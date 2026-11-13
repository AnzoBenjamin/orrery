import {
  AbortMultipartUploadCommand,
  CompleteMultipartUploadCommand,
  CreateMultipartUploadCommand,
  DeleteObjectCommand,
  GetObjectCommand,
  HeadBucketCommand,
  HeadObjectCommand,
  ListMultipartUploadsCommand,
  ListPartsCommand,
  NoSuchKey,
  NoSuchUpload,
  NotFound,
  S3Client,
  S3ServiceException,
  UploadPartCommand,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export interface StorageConfig {
  /** Endpoint the server reaches the store on (inside Docker: http://garage:3900). */
  endpoint: string;
  /** Endpoint browsers reach. Presigned URLs are signed for this host. */
  publicEndpoint: string;
  region: string;
  bucket: string;
  accessKeyId: string;
  secretAccessKey: string;
}

export interface UploadedPart {
  partNumber: number;
  etag: string;
  size: number;
}

export interface PendingMultipartUpload {
  key: string;
  uploadId: string;
  initiatedAt: Date;
}

/** Signed URLs are valid for at most this long (requirement 6.4: short-lived). */
export const MAX_PRESIGN_SECONDS = 15 * 60;

function client(config: StorageConfig, endpoint: string): S3Client {
  return new S3Client({
    endpoint,
    region: config.region,
    credentials: { accessKeyId: config.accessKeyId, secretAccessKey: config.secretAccessKey },
    // Garage serves buckets by path, not by virtual host.
    forcePathStyle: true,
    // Checksums only where S3 requires them. The SDK's default adds CRC32 parameters to presigned
    // part URLs, which a browser upload would then have to reproduce.
    requestChecksumCalculation: "WHEN_REQUIRED",
    responseChecksumValidation: "WHEN_REQUIRED",
  });
}

const isMissing = (error: unknown) =>
  error instanceof NoSuchKey ||
  error instanceof NotFound ||
  error instanceof NoSuchUpload ||
  (error instanceof S3ServiceException && error.$metadata.httpStatusCode === 404);

function clampExpiry(seconds: number): number {
  if (!Number.isInteger(seconds) || seconds < 1) throw new RangeError("expiry must be >= 1 s");
  return Math.min(seconds, MAX_PRESIGN_SECONDS);
}

/**
 * The object store (Garage through the S3 API). One instance per process. Keys come from
 * `keys.ts`; this module does no authorization, so callers must check access first.
 */
export class Storage {
  readonly bucket: string;
  private readonly s3: S3Client;
  private readonly signer: S3Client;

  constructor(config: StorageConfig) {
    this.bucket = config.bucket;
    this.s3 = client(config, config.endpoint);
    this.signer = client(config, config.publicEndpoint);
  }

  async createMultipartUpload(key: string, contentType: string): Promise<string> {
    const out = await this.s3.send(
      new CreateMultipartUploadCommand({ Bucket: this.bucket, Key: key, ContentType: contentType }),
    );
    if (!out.UploadId) throw new Error("CreateMultipartUpload returned no upload id");
    return out.UploadId;
  }

  /** A browser-usable URL that starts a multipart upload (POST ?uploads). */
  presignCreateMultipartUpload(key: string, expiresInSeconds: number): Promise<string> {
    return getSignedUrl(
      this.signer,
      new CreateMultipartUploadCommand({ Bucket: this.bucket, Key: key }),
      { expiresIn: clampExpiry(expiresInSeconds) },
    );
  }

  /** A browser-usable URL that lists the parts uploaded so far, for resuming. */
  presignListParts(key: string, uploadId: string, expiresInSeconds: number): Promise<string> {
    return getSignedUrl(
      this.signer,
      new ListPartsCommand({ Bucket: this.bucket, Key: key, UploadId: uploadId }),
      { expiresIn: clampExpiry(expiresInSeconds) },
    );
  }

  /** A browser-usable URL that assembles the uploaded parts into the object. */
  presignCompleteMultipartUpload(
    key: string,
    uploadId: string,
    expiresInSeconds: number,
  ): Promise<string> {
    return getSignedUrl(
      this.signer,
      new CompleteMultipartUploadCommand({ Bucket: this.bucket, Key: key, UploadId: uploadId }),
      { expiresIn: clampExpiry(expiresInSeconds) },
    );
  }

  /** A browser-usable URL that cancels a multipart upload. */
  presignAbortMultipartUpload(
    key: string,
    uploadId: string,
    expiresInSeconds: number,
  ): Promise<string> {
    return getSignedUrl(
      this.signer,
      new AbortMultipartUploadCommand({ Bucket: this.bucket, Key: key, UploadId: uploadId }),
      { expiresIn: clampExpiry(expiresInSeconds) },
    );
  }

  /** A browser-usable URL that PUTs one part. */
  presignUploadPart(
    key: string,
    uploadId: string,
    partNumber: number,
    expiresInSeconds: number,
  ): Promise<string> {
    return getSignedUrl(
      this.signer,
      new UploadPartCommand({
        Bucket: this.bucket,
        Key: key,
        UploadId: uploadId,
        PartNumber: partNumber,
      }),
      { expiresIn: clampExpiry(expiresInSeconds) },
    );
  }

  /** Every part uploaded so far, in part order. Returns null when the upload no longer exists. */
  async listParts(key: string, uploadId: string): Promise<UploadedPart[] | null> {
    const parts: UploadedPart[] = [];
    let marker: string | undefined;
    try {
      do {
        const out = await this.s3.send(
          new ListPartsCommand({
            Bucket: this.bucket,
            Key: key,
            UploadId: uploadId,
            PartNumberMarker: marker,
          }),
        );
        for (const p of out.Parts ?? []) {
          if (p.PartNumber && p.ETag) {
            parts.push({ partNumber: p.PartNumber, etag: p.ETag, size: p.Size ?? 0 });
          }
        }
        marker = out.IsTruncated ? out.NextPartNumberMarker : undefined;
      } while (marker);
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }
    return parts.sort((a, b) => a.partNumber - b.partNumber);
  }

  async completeMultipartUpload(
    key: string,
    uploadId: string,
    parts: readonly { partNumber: number; etag: string }[],
  ): Promise<void> {
    await this.s3.send(
      new CompleteMultipartUploadCommand({
        Bucket: this.bucket,
        Key: key,
        UploadId: uploadId,
        MultipartUpload: {
          Parts: [...parts]
            .sort((a, b) => a.partNumber - b.partNumber)
            .map((p) => ({ PartNumber: p.partNumber, ETag: p.etag })),
        },
      }),
    );
  }

  /** Aborts an upload. Already-aborted or completed uploads are not an error. */
  async abortMultipartUpload(key: string, uploadId: string): Promise<void> {
    try {
      await this.s3.send(
        new AbortMultipartUploadCommand({ Bucket: this.bucket, Key: key, UploadId: uploadId }),
      );
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
  }

  /** Multipart uploads not yet completed or aborted, optionally under a key prefix. */
  async listMultipartUploads(prefix?: string): Promise<PendingMultipartUpload[]> {
    const uploads: PendingMultipartUpload[] = [];
    let keyMarker: string | undefined;
    let uploadIdMarker: string | undefined;
    do {
      const out = await this.s3.send(
        new ListMultipartUploadsCommand({
          Bucket: this.bucket,
          Prefix: prefix,
          KeyMarker: keyMarker,
          UploadIdMarker: uploadIdMarker,
        }),
      );
      for (const u of out.Uploads ?? []) {
        if (u.Key && u.UploadId && u.Initiated) {
          uploads.push({ key: u.Key, uploadId: u.UploadId, initiatedAt: u.Initiated });
        }
      }
      keyMarker = out.IsTruncated ? out.NextKeyMarker : undefined;
      uploadIdMarker = out.IsTruncated ? out.NextUploadIdMarker : undefined;
    } while (keyMarker);
    return uploads;
  }

  /** The stored size of an object, or null when there is no such object. */
  async objectSize(key: string): Promise<number | null> {
    try {
      const out = await this.s3.send(new HeadObjectCommand({ Bucket: this.bucket, Key: key }));
      return out.ContentLength ?? 0;
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }
  }

  /**
   * A short-lived URL to read an object. Call only after an authorization check (requirement
   * 6.4). `downloadName` makes browsers save the file under that name instead of playing it.
   * URLs for the engine use `audience: "service"`, which signs for the internal endpoint.
   */
  presignGet(
    key: string,
    expiresInSeconds: number,
    options: { downloadName?: string; audience?: "browser" | "service" } = {},
  ): Promise<string> {
    return getSignedUrl(
      options.audience === "service" ? this.s3 : this.signer,
      new GetObjectCommand({
        Bucket: this.bucket,
        Key: key,
        ...(options.downloadName
          ? {
              ResponseContentDisposition: `attachment; filename*=UTF-8''${encodeURIComponent(options.downloadName)}`,
            }
          : {}),
      }),
      { expiresIn: clampExpiry(expiresInSeconds) },
    );
  }

  /**
   * Removes an object and aborts any multipart upload still writing to its key, so a deletion
   * mid-upload leaves nothing behind. Missing objects are not an error.
   */
  async deleteObject(key: string): Promise<void> {
    for (const upload of await this.listMultipartUploads(key)) {
      if (upload.key === key) await this.abortMultipartUpload(key, upload.uploadId);
    }
    try {
      await this.s3.send(new DeleteObjectCommand({ Bucket: this.bucket, Key: key }));
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
  }

  /** Whether the bucket answers with these credentials, within `timeoutMs`. For health checks. */
  async reachable(timeoutMs = 2000): Promise<boolean> {
    try {
      await this.s3.send(new HeadBucketCommand({ Bucket: this.bucket }), {
        abortSignal: AbortSignal.timeout(timeoutMs),
      });
      return true;
    } catch {
      return false;
    }
  }

  destroy(): void {
    this.s3.destroy();
    this.signer.destroy();
  }
}
