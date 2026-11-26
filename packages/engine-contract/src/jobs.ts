import { z } from "zod";

const url = z.string().min(1).max(8192);
const identifier = z.string().min(1).max(200);
const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const traceparent = z.string().regex(/^(?!ff)[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/);

export const reconstructionArtifactSlot = z.literal("analysis_artifacts");

export const artifactUploadGrant = z
  .object({
    uploadUrl: url,
    downloadUrl: url,
  })
  .strict()
  .meta({ id: "ArtifactUploadGrant", title: "ArtifactUploadGrant" });

export const reconstructJobRequest = z
  .object({
    contractVersion: z.string().min(1).max(16),
    jobId: z.uuid(),
    kind: z.literal("reconstruct"),
    inputs: z
      .object({
        footage: z
          .array(
            z
              .object({
                footageId: identifier,
                sourceUrl: url,
                sha256: sha256.optional(),
              })
              .strict(),
          )
          .min(1)
          .max(8),
      })
      .strict(),
    params: z
      .object({
        broken: z.boolean(),
        trackerBackend: z.literal("klt"),
      })
      .strict(),
    artifactGrant: z
      .object({
        analysisArtifacts: artifactUploadGrant,
      })
      .strict(),
    callback: z
      .object({
        url,
        secretRef: identifier,
      })
      .strict(),
    traceparent,
  })
  .strict()
  .meta({ id: "ReconstructJobRequest", title: "ReconstructJobRequest" });

export const jobError = z
  .object({
    code: z.enum([
      "incompatible_contract",
      "capability_unavailable",
      "invalid_input",
      "source_unavailable",
      "artifact_upload_failed",
      "callback_failed",
      "job_not_found",
      "canceled",
      "internal_error",
    ]),
    message: z.string().min(1).max(1000),
    retryable: z.boolean(),
    stage: identifier.optional(),
    prerequisites: z.array(identifier).max(32).optional(),
  })
  .strict()
  .meta({ id: "JobError", title: "JobError" });

export const contractErrorResponse = z
  .object({
    contractVersion: z.literal("1"),
    error: jobError,
  })
  .strict()
  .meta({ id: "ContractErrorResponse", title: "ContractErrorResponse" });

export const jobArtifact = z
  .object({
    slot: reconstructionArtifactSlot,
    mediaType: z.literal("application/vnd.orrery.analysis-artifacts+json"),
    byteSize: z.number().int().nonnegative(),
    sha256,
    downloadUrl: url,
  })
  .strict()
  .meta({ id: "JobArtifact", title: "JobArtifact" });

export const jobAccepted = z
  .object({
    contractVersion: z.literal("1"),
    jobId: z.uuid(),
    accepted: z.literal(true),
    status: z.enum(["queued", "running"]),
    statusUrl: url,
  })
  .strict()
  .meta({ id: "JobAccepted", title: "JobAccepted" });

export const jobRejected = z
  .object({
    contractVersion: z.literal("1"),
    jobId: z.uuid(),
    accepted: z.literal(false),
    status: z.literal("rejected"),
    error: jobError,
  })
  .strict()
  .meta({ id: "JobRejected", title: "JobRejected" });

export const jobSubmissionResponse = z
  .discriminatedUnion("accepted", [jobAccepted, jobRejected])
  .meta({ id: "JobSubmissionResponse", title: "JobSubmissionResponse" });

const activeJobStatus = z
  .object({
    contractVersion: z.literal("1"),
    jobId: z.uuid(),
    status: z.enum(["queued", "running", "awaiting_input"]),
    currentStage: identifier.optional(),
    progress: z.number().min(0).max(1),
    artifacts: z.array(jobArtifact),
  })
  .strict();

const completedJobStatus = z
  .object({
    contractVersion: z.literal("1"),
    jobId: z.uuid(),
    status: z.literal("completed"),
    artifacts: z.array(jobArtifact).min(1),
  })
  .strict();

const failedJobStatus = z
  .object({
    contractVersion: z.literal("1"),
    jobId: z.uuid(),
    status: z.enum(["failed", "canceled"]),
    artifacts: z.array(jobArtifact),
    error: jobError,
  })
  .strict();

export const jobStatus = z
  .union([activeJobStatus, completedJobStatus, failedJobStatus])
  .meta({ id: "JobStatus", title: "JobStatus" });

const eventBase = {
  contractVersion: z.literal("1"),
  jobId: z.uuid(),
  seq: z.number().int().nonnegative(),
  at: z.iso.datetime({ offset: true }),
};

export const engineEvent = z
  .discriminatedUnion("type", [
    z
      .object({
        ...eventBase,
        type: z.literal("stage_started"),
        payload: z.object({ stage: identifier }).strict(),
      })
      .strict(),
    z
      .object({
        ...eventBase,
        type: z.literal("progress"),
        payload: z
          .object({
            stage: identifier,
            fraction: z.number().min(0).max(1),
            description: z.string().min(1).max(500),
            etaSeconds: z.number().nonnegative().optional(),
          })
          .strict(),
      })
      .strict(),
    z
      .object({
        ...eventBase,
        type: z.literal("stage_completed"),
        payload: z
          .object({
            stage: identifier,
            runtimeMs: z.number().nonnegative(),
            peakRssBytes: z.number().int().nonnegative(),
          })
          .strict(),
      })
      .strict(),
    z
      .object({
        ...eventBase,
        type: z.literal("artifact_written"),
        payload: jobArtifact,
      })
      .strict(),
    z
      .object({
        ...eventBase,
        type: z.literal("completed"),
        payload: z.object({ artifacts: z.array(jobArtifact).min(1) }).strict(),
      })
      .strict(),
    z
      .object({
        ...eventBase,
        type: z.literal("failed"),
        payload: jobError,
      })
      .strict(),
  ])
  .meta({ id: "EngineEvent", title: "EngineEvent" });

const trackSample = z
  .object({
    frameIndex: z.number().int().nonnegative(),
    xPx: z.number(),
    yPx: z.number(),
    visible: z.boolean(),
    uncertaintyPx: z.number().positive().optional(),
  })
  .strict();

const trackArtifact = z
  .object({
    trackId: identifier,
    bodyId: identifier,
    samples: z.array(trackSample),
  })
  .strict();

const cameraMotionArtifact = z
  .object({
    frameIndex: z.number().int().nonnegative(),
    referenceToFrame: z.array(z.number()).length(9),
  })
  .strict();

const bodyPoseArtifact = z
  .object({
    frameIndex: z.number().int().nonnegative(),
    xWorld: z.number(),
    yWorld: z.number(),
    angleRadians: z.number(),
  })
  .strict();

const bodyArtifact = z
  .object({
    bodyId: identifier,
    linkLengthWorld: z.number().positive().optional(),
    poses: z.array(bodyPoseArtifact),
  })
  .strict();

const jointArtifact = z
  .object({
    jointId: identifier,
    bodyA: identifier,
    bodyB: identifier,
    kind: identifier,
    xPx: z.number(),
    yPx: z.number(),
  })
  .strict();

const parameterEstimate = z
  .object({
    parameterId: identifier,
    estimate: z.number(),
    standardDeviation: z.number().nonnegative(),
  })
  .strict();

const diagnosisFinding = z
  .object({
    kind: z.enum(["loose_body", "frozen_body", "empty_hole", "missing_joint", "missing_body"]),
    ref: identifier,
  })
  .strict();

const resurrectionCandidate = z
  .object({
    repairKey: identifier,
    rank: z.number().int().positive(),
    tieGroup: identifier.optional(),
  })
  .strict();

const stageRuntime = z
  .object({
    stage: identifier,
    runtimeMs: z.number().nonnegative(),
  })
  .strict();

const embeddedMediaArtifact = z
  .object({
    filename: identifier,
    mediaType: z.string().min(1).max(200),
    encoding: z.literal("base64"),
    byteSize: z.number().int().nonnegative(),
    sha256,
    data: z.string(),
  })
  .strict();

const normalizedFrame = z
  .object({
    frameIndex: z.number().int().nonnegative(),
    timestampSeconds: z.number().nonnegative(),
    sourceFrameIndex: z.number().int().nonnegative(),
    originalTimestampSeconds: z.number().nonnegative(),
  })
  .strict();

const cameraIntrinsics = z
  .object({
    fxPixels: z.number().positive(),
    fyPixels: z.number().positive(),
    cxPixels: z.number().nonnegative(),
    cyPixels: z.number().nonnegative(),
    source: identifier,
  })
  .strict();

const thumbnailArtifact = z
  .object({
    frameIndex: z.number().int().nonnegative(),
    timestampSeconds: z.number().nonnegative(),
    image: embeddedMediaArtifact,
  })
  .strict();

const ingestFootageArtifact = z
  .object({
    footageId: identifier,
    sourceSha256: sha256,
    container: identifier,
    codec: identifier,
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    displayWidth: z.number().int().positive(),
    displayHeight: z.number().int().positive(),
    rotationQuarterTurns: z.number().int().min(0).max(3),
    colorSpace: z.literal("bt709-rgb"),
    originalTimestampsSeconds: z.array(z.number().nonnegative()).min(1),
    normalizedFrames: z.array(normalizedFrame).min(1),
    intrinsics: cameraIntrinsics.optional(),
    analysisCopy: embeddedMediaArtifact,
    proxyVideo: embeddedMediaArtifact,
    thumbnails: z.array(thumbnailArtifact).min(1),
  })
  .strict();

export const analysisArtifacts = z
  .object({
    format: z.literal("orrery.engine.analysis-artifacts"),
    schemaVersion: z.literal(1),
    engineVersion: identifier,
    tracks: z.array(trackArtifact),
    cameraMotion: z.array(cameraMotionArtifact),
    bodies: z.array(bodyArtifact),
    joints: z.array(jointArtifact),
    mobility: z.number().int().optional(),
    parameters: z.array(parameterEstimate),
    diagnosis: z.array(diagnosisFinding),
    resurrection: z.array(resurrectionCandidate),
    stageRuntimes: z.array(stageRuntime),
    ingest: z.array(ingestFootageArtifact).optional(),
  })
  .strict()
  .meta({ id: "AnalysisArtifacts", title: "AnalysisArtifacts" });

export type ReconstructJobRequest = z.input<typeof reconstructJobRequest>;
export type ContractErrorResponse = z.output<typeof contractErrorResponse>;
export type JobSubmissionResponse = z.output<typeof jobSubmissionResponse>;
export type JobStatus = z.output<typeof jobStatus>;
export type EngineEvent = z.output<typeof engineEvent>;
export type AnalysisArtifacts = z.output<typeof analysisArtifacts>;
