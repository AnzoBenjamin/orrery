import { createServerFn } from "@tanstack/react-start";
import { call } from "../server/call.ts";
import {
  footageDelete,
  footageList,
  footagePlayback,
  footageUploadAbort,
  footageUploadComplete,
  footageUploadCreate,
  footageUploadSign,
  footageUsage,
} from "../server/operations/footage.ts";
import { typed } from "./typed.ts";

export const listFootageFn = createServerFn({ method: "GET" })
  .validator(typed(footageList.input))
  .handler(({ data }) => call(footageList, data));

export const getStorageUsageFn = createServerFn({ method: "GET" })
  .validator(typed(footageUsage.input))
  .handler(({ data }) => call(footageUsage, data));

export const createUploadFn = createServerFn({ method: "POST" })
  .validator(typed(footageUploadCreate.input))
  .handler(({ data }) => call(footageUploadCreate, data));

export const signUploadFn = createServerFn({ method: "POST" })
  .validator(typed(footageUploadSign.input))
  .handler(({ data }) => call(footageUploadSign, data));

export const completeUploadFn = createServerFn({ method: "POST" })
  .validator(typed(footageUploadComplete.input))
  .handler(({ data }) => call(footageUploadComplete, data));

export const abortUploadFn = createServerFn({ method: "POST" })
  .validator(typed(footageUploadAbort.input))
  .handler(({ data }) => call(footageUploadAbort, data));

export const deleteFootageFn = createServerFn({ method: "POST" })
  .validator(typed(footageDelete.input))
  .handler(({ data }) => call(footageDelete, data));

export const playbackUrlFn = createServerFn({ method: "POST" })
  .validator(typed(footagePlayback.input))
  .handler(({ data }) => call(footagePlayback, data));
