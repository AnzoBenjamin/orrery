import { createServerFn } from "@tanstack/react-start";
import { call } from "../server/call.ts";
import {
  shareCreate,
  shareList,
  shareOpen,
  sharePlayback,
  shareRevoke,
} from "../server/operations/shares.ts";
import { typed } from "./typed.ts";

export const listSharesFn = createServerFn({ method: "GET" })
  .validator(typed(shareList.input))
  .handler(({ data }) => call(shareList, data));

export const createShareFn = createServerFn({ method: "POST" })
  .validator(typed(shareCreate.input))
  .handler(({ data }) => call(shareCreate, data));

export const revokeShareFn = createServerFn({ method: "POST" })
  .validator(typed(shareRevoke.input))
  .handler(({ data }) => call(shareRevoke, data));

export const openShareFn = createServerFn({ method: "GET" })
  .validator(typed(shareOpen.input))
  .handler(({ data }) => call(shareOpen, data));

export const sharePlaybackFn = createServerFn({ method: "POST" })
  .validator(typed(sharePlayback.input))
  .handler(({ data }) => call(sharePlayback, data));
