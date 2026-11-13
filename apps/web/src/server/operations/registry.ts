import {
  accountDeviceForget,
  accountGet,
  accountPreferencesUpdate,
  accountSessionRevoke,
  accountSessionsRevokeOthers,
} from "./account.ts";
import { adminJobCancel, adminJobRetry, adminOverview } from "./admin.ts";
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
  notificationList,
  notificationMarkAllRead,
  notificationMarkRead,
  notificationUnreadCount,
} from "./notifications.ts";
import { shareCreate, shareList, shareOpen, sharePlayback, shareRevoke } from "./shares.ts";
import {
  specimenCreate,
  specimenDelete,
  specimenEventsOpen,
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
  specimenEventsOpen,
  accountGet,
  accountPreferencesUpdate,
  accountSessionRevoke,
  accountSessionsRevokeOthers,
  accountDeviceForget,
  footageList,
  footageUsage,
  footageUploadCreate,
  footageUploadSign,
  footageUploadComplete,
  footageUploadAbort,
  footageDelete,
  footagePlayback,
  shareList,
  shareCreate,
  shareRevoke,
  shareOpen,
  sharePlayback,
  notificationList,
  notificationUnreadCount,
  notificationMarkRead,
  notificationMarkAllRead,
  adminOverview,
  adminJobRetry,
  adminJobCancel,
];
