"""Validated local and Garage/S3 caches keyed by canonical manifest hash."""

# boto3/botocore do not ship complete inline types; this module is their adapter boundary.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_HASH = re.compile(r"^[0-9a-f]{64}$")


class SuiteCache(Protocol):
    """A complete-suite content-addressed cache."""

    def restore(self, manifest_hash: str, destination: Path) -> bool: ...

    def store(self, manifest_hash: str, source: Path) -> None: ...


class LocalSuiteCache:
    """Deterministic filesystem adapter with the same manifest-hash key semantics as S3."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def restore(self, manifest_hash: str, destination: Path) -> bool:
        _validate_hash(manifest_hash)
        source = self.root / manifest_hash
        if not source.exists():
            return False
        _validate_suite(source, manifest_hash)
        if destination.exists():
            raise FileExistsError(f"cache restore destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{manifest_hash}-", dir=destination.parent))
        shutil.rmtree(temporary)
        try:
            shutil.copytree(source, temporary)
            _validate_suite(temporary, manifest_hash)
            os.replace(temporary, destination)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return True

    def store(self, manifest_hash: str, source: Path) -> None:
        _validate_hash(manifest_hash)
        _validate_suite(source, manifest_hash)
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / manifest_hash
        if destination.exists():
            _validate_suite(destination, manifest_hash)
            return
        temporary = Path(tempfile.mkdtemp(prefix=f".{manifest_hash}-", dir=self.root))
        shutil.rmtree(temporary)
        try:
            shutil.copytree(source, temporary)
            _validate_suite(temporary, manifest_hash)
            os.replace(temporary, destination)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise


class S3SuiteCache:
    """Real S3 API cache, configured for Garage's path-style addressing."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str = "synthetic-lab/suites",
    ) -> None:
        if not bucket or not endpoint_url or not region:
            raise ValueError("S3 cache bucket, endpoint, and region must be non-empty")
        if not access_key_id or not secret_access_key:
            raise ValueError("S3 cache credentials must be non-empty")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if not self.prefix:
            raise ValueError("S3 cache prefix must be non-empty")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def restore(self, manifest_hash: str, destination: Path) -> bool:
        _validate_hash(manifest_hash)
        index_key = self._key(manifest_hash, "suite.json")
        index = self._get(index_key, missing_ok=True)
        if index is None:
            return False
        if destination.exists():
            raise FileExistsError(f"cache restore destination already exists: {destination}")
        paths = tuple(_indexed_paths(index))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{manifest_hash}-", dir=destination.parent))
        try:
            (temporary / "suite.json").write_bytes(index)
            for relative in paths:
                path = temporary / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                body = self._get(self._key(manifest_hash, relative.as_posix()))
                if body is None:
                    raise ValueError(f"S3 suite cache is missing indexed object {relative}")
                path.write_bytes(body)
            _validate_suite(temporary, manifest_hash)
            os.replace(temporary, destination)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return True

    def store(self, manifest_hash: str, source: Path) -> None:
        _validate_hash(manifest_hash)
        _validate_suite(source, manifest_hash)
        files = sorted(path for path in source.rglob("*") if path.is_file())
        index_path = source / "suite.json"
        # The index is the completion marker, so readers never observe a partially uploaded suite.
        for path in files:
            if path != index_path:
                self._put(manifest_hash, path.relative_to(source), path.read_bytes())
        self._put(manifest_hash, Path("suite.json"), index_path.read_bytes())

    def _put(self, manifest_hash: str, relative: Path, body: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(manifest_hash, relative.as_posix()),
            Body=body,
            ContentType=_content_type(relative),
            Metadata={"orrery-manifest-hash": manifest_hash},
        )

    def _get(self, key: str, *, missing_ok: bool = False) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key, ChecksumMode="ENABLED")
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if missing_ok and code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        body = response["Body"]
        try:
            return cast(bytes, body.read())
        finally:
            body.close()

    def _key(self, manifest_hash: str, relative: str) -> str:
        return f"{self.prefix}/{manifest_hash}/{relative}"


def _indexed_paths(index: bytes) -> Iterator[Path]:
    try:
        record = cast(dict[str, object], json.loads(index))
    except json.JSONDecodeError as error:
        raise ValueError("S3 suite cache index is invalid JSON") from error
    files = record.get("files")
    if not isinstance(files, list):
        raise ValueError("S3 suite cache index has no file inventory")
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("S3 suite cache file inventory is invalid")
        relative = Path(cast(str, item["path"]))
        if relative.is_absolute() or ".." in relative.parts or relative == Path("suite.json"):
            raise ValueError("S3 suite cache index contains an unsafe path")
        yield relative


def _validate_hash(value: str) -> None:
    if not _HASH.fullmatch(value):
        raise ValueError("cache key must be a lowercase SHA-256 manifest hash")


def _validate_suite(path: Path, manifest_hash: str) -> None:
    from orrery_lab.suite.generator import (  # noqa: PLC0415 -- avoids import cycle
        read_suite,
    )

    read_suite(path, expected_hash=manifest_hash)


def _content_type(path: Path) -> str:
    return {
        ".json": "application/json",
        ".mp4": "video/mp4",
        ".arrow": "application/vnd.apache.arrow.file",
        ".png": "image/png",
        ".exr": "image/x-exr",
    }.get(path.suffix, "application/octet-stream")


__all__ = ["LocalSuiteCache", "S3SuiteCache", "SuiteCache"]
