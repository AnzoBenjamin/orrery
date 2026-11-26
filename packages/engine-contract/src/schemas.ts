import {
  analysisArtifacts,
  artifactUploadGrant,
  contractErrorResponse,
  engineEvent,
  jobAccepted,
  jobArtifact,
  jobError,
  jobRejected,
  jobStatus,
  jobSubmissionResponse,
  reconstructJobRequest,
} from "./jobs.ts";
import { probeAccepted, probeRejected, probeRequest, probeResponse } from "./probe.ts";

/** Bumped on any breaking change; the engine reports the version it was generated from. */
export const CONTRACT_VERSION = "1";

/** Every schema the engine needs, emitted together so shared definitions appear once. */
export const contractSchemas = {
  probeRequest,
  probeAccepted,
  probeRejected,
  probeResponse,
  reconstructJobRequest,
  artifactUploadGrant,
  jobError,
  contractErrorResponse,
  jobArtifact,
  jobAccepted,
  jobRejected,
  jobSubmissionResponse,
  jobStatus,
  engineEvent,
  analysisArtifacts,
};
