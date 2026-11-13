import { partSizeFor } from "@orrery/storage/limits";
import { Banner, Button, Radio, RadioGroup, useHydrated } from "@orrery/ui";
import AwsS3 from "@uppy/aws-s3";
import Uppy, { type UppyFile } from "@uppy/core";
import GoldenRetriever from "@uppy/golden-retriever";
import { useEffect, useRef, useState } from "react";
import { DropZone, FileTrigger, ProgressBar, Text } from "react-aria-components";
import {
  abortUploadFn,
  completeUploadFn,
  createUploadFn,
  signUploadFn,
} from "../functions/footage.ts";
import { footageRoleOrder, footageRoles } from "../lib/footage-roles.ts";
import { formatBytes } from "../lib/format.ts";
import { failureMessage } from "../lib/result.ts";
import type { FootageRoleName } from "../server/operations/footage.ts";

/** Largest accepted file (requirement 6.3). Mirrors MAX_FOOTAGE_BYTES on the server. */
const MAX_BYTES = 1_000_000_000;

type FileMeta = {
  footageId?: string;
  objectKey?: string;
  role?: FootageRoleName;
};
type Body = Record<string, never>;
type Upload = UppyFile<FileMeta, Body>;

interface Row {
  id: string;
  name: string;
  size: number;
  role: FootageRoleName | undefined;
  footageId: string | undefined;
  percent: number;
  bytesUploaded: number;
  paused: boolean;
  ghost: boolean;
  error: string | null;
  finishing: boolean;
}

/** Maps one S3 request Uppy wants signed onto the server's signing operation. */
function stepOf(request: {
  method: string;
  uploadId?: string;
  partNumber?: number;
}):
  | { step: "create" }
  | { step: "part"; uploadId: string; partNumber: number }
  | { step: "list-parts" | "complete" | "abort"; uploadId: string } {
  const { method, uploadId, partNumber } = request;
  if (!uploadId) {
    if (method === "POST") return { step: "create" };
    throw new Error("Footage is always uploaded in parts.");
  }
  if (method === "PUT" && partNumber !== undefined) return { step: "part", uploadId, partNumber };
  if (method === "GET") return { step: "list-parts", uploadId };
  if (method === "POST") return { step: "complete", uploadId };
  if (method === "DELETE") return { step: "abort", uploadId };
  throw new Error(`Unexpected upload request ${method}`);
}

interface Hooks {
  onChanged: () => Promise<void>;
  onNotice: (message: string) => void;
  onOffline: (offline: boolean) => void;
}

const idle: Hooks = {
  onChanged: async () => undefined,
  onNotice: () => undefined,
  onOffline: () => undefined,
};

interface Uploader {
  uppy: Uppy<FileMeta, Body>;
  hooks: Hooks;
  role: FootageRoleName;
}

/**
 * One uploader per specimen for the life of the page, so uploads keep going while the user
 * moves around the app. Golden Retriever carries them across reloads.
 */
const uploaders = new Map<string, Uploader>();

function uploaderFor(specimenId: string): Uploader {
  const existing = uploaders.get(specimenId);
  if (existing) return existing;
  const uppy = new Uppy<FileMeta, Body>({
    id: `footage-${specimenId}`,
    autoProceed: false,
    restrictions: { maxFileSize: MAX_BYTES },
    // Only files the server has accepted (and given a footage id) are uploaded.
    onBeforeUpload: (files) =>
      Object.fromEntries(Object.entries(files).filter(([, f]) => Boolean(f.meta.footageId))),
  });
  const uploader: Uploader = { uppy, hooks: idle, role: "reference" };
  uppy.use(AwsS3<FileMeta, Body>, {
    shouldUseMultipart: true,
    limit: 2,
    getChunkSize: ({ size }) => partSizeFor(size),
    generateObjectKey: (file) => file.meta.objectKey ?? "",
    signRequest: async (request) => {
      const file = uppy.getFiles().find((f) => f.meta.objectKey === request.key);
      if (!file?.meta.footageId) throw new Error("This file is not registered for upload.");
      const result = await signUploadFn({
        data: { footageId: file.meta.footageId, request: stepOf(request) },
      });
      if (!result.ok) throw new Error(failureMessage(result) ?? "The upload was refused.");
      return { url: result.value.url, key: result.value.key };
    },
  });
  uppy.use(GoldenRetriever, { expires: 24 * 60 * 60 * 1000 });

  uppy.on("file-added", async (file: Upload) => {
    if (file.meta.footageId) {
      // The same file chosen again after a reload: continue from the last finished part.
      await uppy.upload();
      return;
    }
    const role = uploader.role;
    const result = await createUploadFn({
      data: { specimenId, role, filename: file.name, byteSize: file.size ?? 0 },
    });
    if (!result.ok) {
      uppy.removeFile(file.id);
      uploader.hooks.onNotice(
        `${file.name}: ${failureMessage(result) ?? "It could not be added."}`,
      );
      return;
    }
    uppy.setFileMeta(file.id, {
      footageId: result.value.footageId,
      objectKey: result.value.key,
      role,
    });
    await uploader.hooks.onChanged();
    await uppy.upload();
  });
  uppy.on("restriction-failed", (file, error) => {
    uploader.hooks.onNotice(
      `${file?.name ?? "That file"}: ${
        /size/i.test(error.message)
          ? "Footage must be 1 GB or smaller. Trim the clip or export it at a lower bitrate."
          : error.message
      }`,
    );
  });
  uppy.on("upload-success", async (file) => {
    const footageId = file?.meta.footageId;
    if (!file || !footageId) return;
    const result = await completeUploadFn({ data: { footageId } });
    if (!result.ok) {
      uploader.hooks.onNotice(
        `${file.name}: ${failureMessage(result) ?? "It could not be finished."}`,
      );
      return;
    }
    uppy.removeFile(file.id);
    await uploader.hooks.onChanged();
  });
  uppy.on("is-offline", () => uploader.hooks.onOffline(true));
  uppy.on("back-online", () => {
    uploader.hooks.onOffline(false);
    void uppy.retryAll();
  });
  uploaders.set(specimenId, uploader);
  return uploader;
}

function rowsOf(uppy: Uppy<FileMeta, Body>): Row[] {
  return uppy.getFiles().map((f) => ({
    id: f.id,
    name: f.name,
    size: f.size ?? 0,
    role: f.meta.role,
    footageId: f.meta.footageId,
    percent: f.progress.percentage ?? 0,
    bytesUploaded: Number(f.progress.bytesUploaded) || 0,
    paused: Boolean(f.isPaused),
    ghost: f.isGhost,
    error: f.error ?? null,
    finishing: Boolean(f.progress.uploadComplete),
  }));
}

/**
 * Resumable footage upload (requirements 6.1 and 6.2, workbench 5.1): Uppy uploads each file
 * straight to the object store in parts signed by the server. Interrupted uploads resume from the
 * last finished part when the connection returns, and after a reload once the same file is
 * chosen again.
 */
export function FootageUploader(props: { specimenId: string; onChanged: () => Promise<void> }) {
  const hydrated = useHydrated();
  const [role, setRole] = useState<FootageRoleName>("reference");
  const [uploader, setUploader] = useState<Uploader | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const onChanged = useRef(props.onChanged);
  onChanged.current = props.onChanged;

  useEffect(() => {
    const current = uploaderFor(props.specimenId);
    current.hooks = {
      onChanged: () => onChanged.current(),
      onNotice: setNotice,
      onOffline: setOffline,
    };
    const sync = () => setRows(rowsOf(current.uppy));
    current.uppy.on("state-update", sync);
    sync();
    setUploader(current);
    return () => {
      current.uppy.off("state-update", sync);
      current.hooks = idle;
    };
  }, [props.specimenId]);

  useEffect(() => {
    if (uploader) uploader.role = role;
  }, [uploader, role]);

  const uppy = uploader?.uppy ?? null;

  function addFiles(files: File[]) {
    setNotice(null);
    for (const data of files) {
      try {
        uppy?.addFile({ name: data.name, type: data.type, data, source: "local" });
      } catch {
        // Restriction failures are reported through the restriction-failed event.
      }
    }
  }

  const ready = hydrated && uppy !== null;

  async function cancel(row: Row) {
    uppy?.removeFile(row.id);
    if (row.footageId) {
      await abortUploadFn({ data: { footageId: row.footageId } });
      await props.onChanged();
    }
  }

  return (
    <section aria-labelledby="add-footage-title" className="flex flex-col gap-5">
      <h2 id="add-footage-title" className="font-display text-2xl text-bone">
        Add footage
      </h2>
      <RadioGroup
        label="What does this footage show?"
        value={role}
        onChange={(value) => setRole(value as FootageRoleName)}
        description={footageRoles[role].hint}
      >
        {footageRoleOrder.map((r) => (
          <Radio key={r} value={r}>
            {footageRoles[r].label}
          </Radio>
        ))}
      </RadioGroup>
      <DropZone
        isDisabled={!ready}
        getDropOperation={() => "copy"}
        onDrop={async (event) => {
          const files: File[] = [];
          for (const item of event.items) {
            if (item.kind === "file") files.push(await item.getFile());
          }
          addFiles(files);
        }}
        className="flex flex-col items-center gap-3 border border-brass/60 border-dashed px-6 py-10 text-center data-[drop-target]:border-brass-bright data-[drop-target]:bg-umber/40"
      >
        <Text slot="label" className="font-display text-bone text-xl">
          Drop video files here
        </Text>
        <p className="max-w-md text-parchment text-sm">
          MP4, MOV, MKV, WebM, or AVI, up to 1 GB and 5 minutes each. Uploads continue through a
          dropped connection.
        </p>
        <FileTrigger
          allowsMultiple
          acceptedFileTypes={["video/*", ".mp4", ".mov", ".mkv", ".webm", ".avi"]}
          onSelect={(list) => addFiles(list ? Array.from(list) : [])}
        >
          <Button variant="secondary" isDisabled={!ready}>
            Choose files
          </Button>
        </FileTrigger>
      </DropZone>
      {offline ? (
        <Banner tone="info" title="Connection lost.">
          Uploads pause and continue from the last finished part when you are back online.
        </Banner>
      ) : null}
      {notice ? <Banner tone="error" title={notice} /> : null}
      {rows.length > 0 ? (
        <ul aria-label="Uploads" className="flex flex-col gap-3">
          {rows.map((row) => (
            <UploadRow key={row.id} row={row} uppy={uppy} onCancel={() => cancel(row)} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function UploadRow(props: {
  row: Row;
  uppy: Uppy<FileMeta, Body> | null;
  onCancel: () => Promise<void>;
}) {
  const { row, uppy } = props;
  const state = row.ghost
    ? `Interrupted at ${row.percent}%. Choose ${row.name} again to continue.`
    : row.error
      ? `Failed: ${row.error}`
      : row.finishing
        ? "Finishing…"
        : row.paused
          ? `Paused at ${row.percent}%`
          : `Uploading, ${formatBytes(row.bytesUploaded)} of ${formatBytes(row.size)}`;
  return (
    <li aria-label={row.name} className="border border-umber bg-soot px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="min-w-0 break-all font-instrument text-bone text-sm">{row.name}</p>
        {row.role ? (
          <span className="font-display-sc text-parchment text-sm tracking-[0.1em]">
            {footageRoles[row.role].label}
          </span>
        ) : null}
      </div>
      <ProgressBar
        aria-label={`Upload of ${row.name}`}
        value={row.percent}
        className="mt-2 h-1.5 w-full bg-umber"
      >
        {({ percentage }) => (
          <div
            className={`h-full ${row.error ? "bg-oxblood" : "bg-brass"}`}
            style={{ width: `${percentage ?? 0}%` }}
          />
        )}
      </ProgressBar>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <p className="text-parchment text-sm" aria-live="polite">
          {state}
        </p>
        <div className="flex gap-5">
          {row.error ? (
            <Button variant="quiet" onPress={() => void uppy?.retryUpload(row.id)}>
              Retry
            </Button>
          ) : null}
          {!row.ghost && !row.error && !row.finishing ? (
            <Button variant="quiet" onPress={() => uppy?.pauseResume(row.id)}>
              {row.paused ? "Resume" : "Pause"}
            </Button>
          ) : null}
          {!row.finishing ? (
            <Button
              variant="quiet"
              aria-label={`Cancel ${row.name}`}
              onPress={() => void props.onCancel()}
            >
              Cancel
            </Button>
          ) : null}
        </div>
      </div>
    </li>
  );
}
