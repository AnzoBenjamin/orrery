/**
 * The solver worker's entry point: `new Worker(new URL("@orrery/kinematics-wasm/worker",
 * import.meta.url), { type: "module" })`. Loads the WebAssembly module, then serves requests.
 */
import init, { fit, Solver } from "../pkg/kinematics.js";
import { serve } from "./host.ts";

declare const self: DedicatedWorkerGlobalScope;

await init({ module_or_path: new URL("../pkg/kinematics_bg.wasm", import.meta.url) });
serve(self, { Solver, fit });
