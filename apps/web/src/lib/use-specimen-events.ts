import { useEffect, useRef } from "react";

export type SpecimenEventType = "footage.changed" | "specimen.changed";

/**
 * Subscribes to a specimen's live events (requirement 8.3). EventSource reconnects by itself and
 * sends Last-Event-ID, so the server replays whatever was missed while disconnected.
 */
export function useSpecimenEvents(
  specimenId: string,
  onEvent: (type: SpecimenEventType, payload: unknown) => void,
) {
  const handler = useRef(onEvent);
  handler.current = onEvent;
  useEffect(() => {
    const source = new EventSource(`/api/specimens/${specimenId}/events`);
    const listen = (type: SpecimenEventType) => (event: MessageEvent<string>) => {
      let payload: unknown = null;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      handler.current(type, payload);
    };
    const types: SpecimenEventType[] = ["footage.changed", "specimen.changed"];
    const listeners = types.map((t) => [t, listen(t)] as const);
    for (const [t, l] of listeners) source.addEventListener(t, l);
    return () => {
      for (const [t, l] of listeners) source.removeEventListener(t, l);
      source.close();
    };
  }, [specimenId]);
}
