import { createServerFn } from "@tanstack/react-start";
import { call } from "../server/call.ts";
import {
  accountGet,
  accountPreferencesUpdate,
  accountSessionRevoke,
  accountSessionsRevokeOthers,
} from "../server/operations/account.ts";
import { typed } from "./typed.ts";

export const getAccountFn = createServerFn({ method: "GET" })
  .validator(typed(accountGet.input))
  .handler(({ data }) => call(accountGet, data));

export const updatePreferencesFn = createServerFn({ method: "POST" })
  .validator(typed(accountPreferencesUpdate.input))
  .handler(({ data }) => call(accountPreferencesUpdate, data));

export const revokeSessionFn = createServerFn({ method: "POST" })
  .validator(typed(accountSessionRevoke.input))
  .handler(({ data }) => call(accountSessionRevoke, data));

export const revokeOtherSessionsFn = createServerFn({ method: "POST" })
  .validator(typed(accountSessionsRevokeOthers.input))
  .handler(({ data }) => call(accountSessionsRevokeOthers, data));
