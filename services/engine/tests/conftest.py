import hashlib
import hmac
import json
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

CALLBACK_SECRET = "s" * 40


@dataclass
class JobServer:
    origin: str
    artifact: bytes | None = None
    events: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    put_count: int = 0
    signatures_verified: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Real encoded media made with FFmpeg, one file per case."""
    root = tmp_path_factory.mktemp("clips")
    h264 = root / "h264.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30", "-t", "2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(h264),
    )  # fmt: skip
    rotated = root / "rotated.mp4"
    ffmpeg("-display_rotation", "90", "-i", str(h264), "-c", "copy", str(rotated))
    webm = root / "vp9.webm"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25", "-t", "1",
        "-c:v", "libvpx-vp9", "-deadline", "realtime", str(webm),
    )  # fmt: skip
    vfr = root / "vfr.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30", "-t", "2",
        "-vf", "select='if(lt(t,1),1,not(mod(n,2)))'", "-fps_mode", "vfr",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(vfr),
    )  # fmt: skip
    audio = root / "tone.m4a"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-c:a", "aac", str(audio))
    disguised = root / "notes.mp4"
    disguised.write_text("Bobbin winder seized; hand wheel turns. " * 200)
    gif = root / "loop.gif"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=64x48:rate=10", "-t", "1", str(gif))
    return {
        "h264": h264,
        "rotated": rotated,
        "webm": webm,
        "vfr": vfr,
        "audio": audio,
        "disguised": disguised,
        "gif": gif,
    }


@pytest.fixture(scope="session")
def file_server(clips: dict[str, Path]) -> Iterator[str]:
    """A real HTTP server for the clips, standing in for the object store's presigned GETs."""
    directory = next(iter(clips.values())).parent
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="session")
def job_server(clips: dict[str, Path]) -> Iterator[JobServer]:
    """Real grant and callback server; it verifies callback HMAC before accepting events."""
    state = JobServer("")
    directory = next(iter(clips.values())).parent

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            name = self.path.split("?", 1)[0].removeprefix("/")
            path = directory / name
            if name == "analysis.json" and state.artifact is not None:
                self._send(state.artifact, "application/json")
                return
            if name == "slow.mp4":
                content = (directory / "h264.mp4").read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                for offset in range(0, len(content), 128):
                    self.wfile.write(content[offset : offset + 128])
                    self.wfile.flush()
                    time.sleep(0.02)
                return
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send(path.read_bytes(), "video/mp4")

        def do_PUT(self) -> None:
            content = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            with state.lock:
                state.artifact = content
                state.put_count += 1
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

        def do_POST(self) -> None:
            content = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            timestamp = self.headers.get("Orrery-Callback-Timestamp", "")
            signature = self.headers.get("Orrery-Callback-Signature", "")
            expected = hmac.new(
                CALLBACK_SECRET.encode(), timestamp.encode() + b"." + content, hashlib.sha256
            ).hexdigest()
            if (
                signature != f"sha256={expected}"
                or not timestamp.isdigit()
                or abs(time.time() - int(timestamp)) > 300
            ):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            event = json.loads(content)
            with state.lock:
                state.events.append(event)
                state.signatures_verified += 1
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

        def _send(self, content: bytes, media_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.origin = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state
    server.shutdown()
