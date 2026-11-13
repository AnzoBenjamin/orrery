import {
  accountGet,
  accountPreferencesUpdate,
  accountSessionRevoke,
  accountSessionsRevokeOthers,
} from "./account.ts";
import type { AnyOperation } from "./define.ts";
import {
  footageDelete,
  footageList,
  footagePlayback,
  footageUploadAbort,
  footageUploadComplete,
  footageUploadCreate,
  footageUploadSign,
  footageUsage,
} from "./footage.ts";
import {
  specimenCreate,
  specimenDelete,
  specimenGet,
  specimenList,
  specimenUpdate,
} from "./specimens.ts";

/**
 * Every operation exposed through a server function. The cross-user authorization test
 * (property 1) iterates this list and fails for any entry without a case.
 */
export const operations: readonly AnyOperation[] = [
  specimenCreate,
  specimenList,
  specimenGet,
  specimenUpdate,
  specimenDelete,
  accountGet,
  accountPreferencesUpdate,
  accountSessionRevoke,
  accountSessionsRevokeOthers,
  footageList,
  footageUsage,
  footageUploadCreate,
  footageUploadSign,
  footageUploadComplete,
  footageUploadAbort,
  footageDelete,
  footagePlayback,
];
