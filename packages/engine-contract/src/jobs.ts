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

const pointAnnotation = z
  .object({
    annotationId: identifier,
    footageId: identifier,
    frameIndex: z.number().int().nonnegative(),
    kind: z.enum(["joint", "part_prompt"]),
    point: z
      .object({
        xPx: z.number().nonnegative(),
        yPx: z.number().nonnegative(),
      })
      .strict(),
    coordinateSpace: z.literal("full_resolution_pixels"),
  })
  .strict();

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
        annotations: z.array(pointAnnotation).max(10000).optional(),
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
      "requires_spatial",
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
        type: z.literal("routing"),
        payload: z
          .object({
            stage: identifier,
            destination: z.literal("spatial_reconstruction"),
            reason: z.string().min(1).max(1000),
          })
          .strict(),
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
    xPx: z.number().optional(),
    yPx: z.number().optional(),
    visible: z.boolean(),
    confidence: z.number().min(0).max(1),
    status: z.enum(["observed", "occluded", "lost", "not_seeded"]),
    rejectionReason: z
      .enum(["lk_failure", "forward_backward", "appearance", "out_of_bounds"])
      .optional(),
    uncertaintyPx: z.number().positive().optional(),
  })
  .strict()
  .superRefine((sample, context) => {
    const hasX = sample.xPx !== undefined;
    const hasY = sample.yPx !== undefined;
    if (
      hasX !== hasY ||
      sample.visible !== (sample.status === "observed") ||
      hasX !== sample.visible
    ) {
      context.addIssue({
        code: "custom",
        message: "only observed track samples may contain a complete position",
      });
    }
  });

const trackArtifact = z
  .object({
    trackId: identifier,
    footageId: identifier,
    seedId: identifier,
    regionId: identifier.optional(),
    source: z.enum([
      "shi_tomasi",
      "circular_hole",
      "user_joint",
      "user_part_prompt",
      "reseeded_shi_tomasi",
    ]),
    bodyId: identifier.optional(),
    samples: z.array(trackSample).min(1),
  })
  .strict();

const cameraMotionArtifact = z
  .object({
    frameIndex: z.number().int().nonnegative(),
    footageId: identifier.optional(),
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

const cameraMotionQuality = z
  .object({
    stabilizedRmsPx: z.number().nonnegative(),
    medianResidualPx: z.number().nonnegative(),
    p95ResidualPx: z.number().nonnegative(),
    meanInlierRatio: z.number().min(0).max(1),
    validFrameFraction: z.number().min(0).max(1),
    staticPixelFraction: z.number().min(0).max(1),
    parallaxEvidenceFrames: z.number().int().nonnegative(),
  })
  .strict();

const cameraMotionFootageArtifact = z
  .object({
    footageId: identifier,
    referenceFrameIndex: z.number().int().nonnegative(),
    referenceSource: z.enum(["static_scene", "ground_tracks"]),
    groundRefinementAvailable: z.literal(true),
    requiresSpatial: z.boolean(),
    routingReason: z.string().min(1).max(1000).optional(),
    staticMask: embeddedMediaArtifact,
    stabilizedPreview: embeddedMediaArtifact,
    quality: cameraMotionQuality,
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

const seedingReseedingPolicy = z
  .object({
    intervalFrames: z.number().int().positive(),
    regionalCoverageThreshold: z.number().min(0).max(1),
  })
  .strict();

const seedPointArtifact = z
  .object({
    seedId: identifier,
    xPx: z.number().nonnegative(),
    yPx: z.number().nonnegative(),
    source: z.enum([
      "shi_tomasi",
      "circular_hole",
      "user_joint",
      "user_part_prompt",
      "reseeded_shi_tomasi",
    ]),
    type: z.enum(["corner", "hole", "pivot", "prompt"]),
    confidence: z.number().min(0).max(1),
    frameIndex: z.number().int().nonnegative(),
    detectionScale: z.enum(["analysis", "full_resolution", "user_full_resolution"]),
    regionId: identifier.optional(),
    sourceXPx: z.number().nonnegative().optional(),
    sourceYPx: z.number().nonnegative().optional(),
    annotationId: identifier.optional(),
  })
  .strict();

const seedingCoverageArtifact = z
  .object({
    regionId: identifier,
    boundingBox: z.array(z.number().int().nonnegative()).length(4),
    movingPixelCount: z.number().int().nonnegative(),
    eligibleCellCount: z.number().int().nonnegative(),
    coveredCellCount: z.number().int().nonnegative(),
    seedCount: z.number().int().nonnegative(),
    coverageFraction: z.number().min(0).max(1),
  })
  .strict();

const seedingFootageArtifact = z
  .object({
    format: z.literal("orrery.engine.seeding"),
    schemaVersion: z.literal(1),
    footageId: identifier,
    coordinateSpace: z.literal("analysis_pixels"),
    analysisWidth: z.number().int().positive(),
    analysisHeight: z.number().int().positive(),
    sourceWidth: z.number().int().positive(),
    sourceHeight: z.number().int().positive(),
    scaleXFromSource: z.number().positive(),
    scaleYFromSource: z.number().positive(),
    keyFrameIndices: z.array(z.number().int().nonnegative()).min(1),
    movingMask: embeddedMediaArtifact,
    points: z.array(seedPointArtifact),
    coverage: z.array(seedingCoverageArtifact),
    reseedingPolicy: seedingReseedingPolicy,
  })
  .strict();

const trackingMetrics = z
  .object({
    inputSeedCount: z.number().int().nonnegative(),
    outputTrackCount: z.number().int().nonnegative(),
    reseededTrackCount: z.number().int().nonnegative(),
    observedSampleCount: z.number().int().nonnegative(),
    observedFraction: z.number().min(0).max(1),
    forwardBackwardRejections: z.number().int().nonnegative(),
    appearanceRejections: z.number().int().nonnegative(),
    lkRejections: z.number().int().nonnegative(),
    boundaryRejections: z.number().int().nonnegative(),
  })
  .strict();

const trackingReseedCoverage = z
  .object({
    regionId: identifier,
    baselineSeedCount: z.number().int().nonnegative(),
    liveSeedCount: z.number().int().nonnegative(),
    addedSeedCount: z.number().int().nonnegative(),
    coverageBefore: z.number().min(0).max(1),
    coverageAfter: z.number().min(0).max(1),
  })
  .strict();

const trackingReseedEvent = z
  .object({
    frameIndex: z.number().int().nonnegative(),
    coverage: z.array(trackingReseedCoverage),
    addedSeedIds: z.array(identifier),
  })
  .strict();

const trackingFootageArtifact = z
  .object({
    format: z.literal("orrery.engine.tracking"),
    schemaVersion: z.literal(1),
    footageId: identifier,
    backend: z.literal("klt"),
    coordinateSpace: z.literal("analysis_pixels"),
    analysisWidth: z.number().int().positive(),
    analysisHeight: z.number().int().positive(),
    frameCount: z.number().int().positive(),
    tracksArrow: embeddedMediaArtifact,
    metrics: trackingMetrics,
    reseeding: z.array(trackingReseedEvent),
  })
  .strict();

export const analysisArtifacts = z
  .object({
    format: z.literal("orrery.engine.analysis-artifacts"),
    schemaVersion: z.literal(1),
    engineVersion: identifier,
    tracks: z.array(trackArtifact),
    cameraMotion: z.array(cameraMotionArtifact),
    cameraMotionAnalysis: z.array(cameraMotionFootageArtifact).optional(),
    seedingAnalysis: z.array(seedingFootageArtifact).optional(),
    trackingAnalysis: z.array(trackingFootageArtifact).optional(),
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
