export {
  MAX_PRESIGN_SECONDS,
  type PendingMultipartUpload,
  Storage,
  type StorageConfig,
  type UploadedPart,
} from "./client.ts";
export { footageObjectKey, specimenPrefix, storedExtension } from "./keys.ts";
export {
  MAX_FOOTAGE_BYTES,
  MAX_FOOTAGE_DURATION_S,
  MAX_PARTS,
  MIN_PART_BYTES,
  PREFERRED_PART_BYTES,
  partCount,
  partSizeFor,
  UPLOAD_TTL_SECONDS,
} from "./limits.ts";
