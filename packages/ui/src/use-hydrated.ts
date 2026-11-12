import { useSyncExternalStore } from "react";

const subscribe = () => () => undefined;

/**
 * False during server rendering and the hydration pass, true afterwards. Forms whose submission
 * runs in JavaScript disable their submit button until then, so an early click cannot fall back to
 * a native form submission.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
