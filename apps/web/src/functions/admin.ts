import { createServerFn } from "@tanstack/react-start";
import { call } from "../server/call.ts";
import { adminJobCancel, adminJobRetry, adminOverview } from "../server/operations/admin.ts";
import { typed } from "./typed.ts";

export const adminOverviewFn = createServerFn({ method: "GET" })
  .validator(typed(adminOverview.input))
  .handler(({ data }) => call(adminOverview, data));

export const retryJobFn = createServerFn({ method: "POST" })
  .validator(typed(adminJobRetry.input))
  .handler(({ data }) => call(adminJobRetry, data));

export const cancelJobFn = createServerFn({ method: "POST" })
  .validator(typed(adminJobCancel.input))
  .handler(({ data }) => call(adminJobCancel, data));
