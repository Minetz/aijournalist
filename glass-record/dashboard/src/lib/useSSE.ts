"use client";

import { useEffect, useRef, useState } from "react";

export interface CycleEvent {
  event: string;
  data: Record<string, unknown>;
  ts: string;
}

const EDITOR_URL =
  process.env.NEXT_PUBLIC_EDITOR_URL ?? "http://localhost:8000";

/**
 * Subscribe to the Editor service's SSE stream for a journalist.
 *
 * Returns:
 *  - events: last N cycle events received in this session
 *  - status: current cycle status derived from the event stream
 *  - connected: whether the SSE connection is open
 */
export function useSSE(journalistId: string, maxEvents = 50) {
  const [events, setEvents] = useState<CycleEvent[]>([]);
  const [status, setStatus] = useState<string>("idle");
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!journalistId) return;

    const url = `${EDITOR_URL}/stream/${encodeURIComponent(journalistId)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setConnected(true);

    es.onmessage = (e) => {
      try {
        const payload: CycleEvent = JSON.parse(e.data);
        setEvents((prev) =>
          [payload, ...prev].slice(0, maxEvents)
        );
        // Derive human-readable status from event type
        setStatus(eventToStatus(payload.event));
      } catch {
        // Ignore malformed events
      }
    };

    es.onerror = () => {
      setConnected(false);
      // EventSource auto-reconnects — no manual retry needed
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [journalistId, maxEvents]);

  return { events, status, connected };
}

function eventToStatus(event: string): string {
  const map: Record<string, string> = {
    cycle_start: "Starting cycle…",
    llm_call: "Thinking…",
    story_selected: "Story selected",
    mandate_decomposed: "Researching…",
    researchers_spawned: "Researchers active",
    research_complete: "Research complete",
    compliance_result: "Compliance check done",
    building_legal_tree: "Building legal tree…",
    legal_tree_ready: "Legal tree ready",
    story_published: "Published",
    cycle_complete: "Idle",
    cycle_error: "Error",
  };
  return map[event] ?? "Active";
}
