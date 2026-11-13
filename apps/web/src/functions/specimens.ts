import { createServerFn } from "@tanstack/react-start";
import { call } from "../server/call.ts";
import {
  specimenCreate,
  specimenDelete,
  specimenGet,
  specimenList,
  specimenUpdate,
} from "../server/operations/specimens.ts";
import { typed } from "./typed.ts";

export const createSpecimenFn = createServerFn({ method: "POST" })
  .validator(typed(specimenCreate.input))
  .handler(({ data }) => call(specimenCreate, data));

export const listSpecimensFn = createServerFn({ method: "GET" })
  .validator(typed(specimenList.input))
  .handler(({ data }) => call(specimenList, data));

export const getSpecimenFn = createServerFn({ method: "GET" })
  .validator(typed(specimenGet.input))
  .handler(({ data }) => call(specimenGet, data));

export const updateSpecimenFn = createServerFn({ method: "POST" })
  .validator(typed(specimenUpdate.input))
  .handler(({ data }) => call(specimenUpdate, data));

export const deleteSpecimenFn = createServerFn({ method: "POST" })
  .validator(typed(specimenDelete.input))
  .handler(({ data }) => call(specimenDelete, data));
