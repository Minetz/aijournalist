"use client";

import { useMemo } from "react";
import type { CycleEvent } from "@/lib/useSSE";

type StageStatus = "pending" | "active" | "done" | "error";

interface Stage {
  id: string;
  label: string;
  status: StageStatus;
  detail?: string;
}

const STAGE_ORDER = ["select", "decompose", "research", "compliance", "legal_tree", "publish"];

// ── Public component ─────────────────────────────────────────────────────────

export function PipelineDiagram({
  events,
  cycleStatus,
}: {
  events: CycleEvent[];
  cycleStatus?: string;
}) {
  const stages = useMemo(
    () => computeStages(events, cycleStatus),
    [events, cycleStatus],
  );

  const anyActive = stages.some((s) => s.status === "active");
  const allDone = stages.every((s) => s.status === "done");
  const hasError = stages.some((s) => s.status === "error");

  return (
    <div className="space-y-4">
      {/* Summary line */}
      <p className="text-xs text-gray-400">
        {allDone
          ? "Cycle complete — article published."
          : hasError
          ? "Cycle blocked — compliance check failed."
          : anyActive
          ? "Cycle running…"
          : "Waiting for next cycle."}
      </p>

      {/* Stage flow */}
      <div className="w-full overflow-x-auto">
        <div className="flex items-start gap-1 min-w-max">
          {stages.map((stage, i) => (
            <div key={stage.id} className="flex items-center gap-1">
              <StageBox stage={stage} />
              {i < stages.length - 1 && (
                <span className="text-gray-300 text-xs mt-3 px-0.5">→</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Stage box ────────────────────────────────────────────────────────────────

function StageBox({ stage }: { stage: Stage }) {
  const border = {
    pending: "border-gray-200 bg-white",
    active: "border-blue-400 bg-blue-50 shadow-sm shadow-blue-100",
    done: "border-green-300 bg-green-50",
    error: "border-red-300 bg-red-50",
  }[stage.status];

  const dot = {
    pending: "bg-gray-300",
    active: "bg-blue-500 animate-pulse",
    done: "bg-green-500",
    error: "bg-red-500",
  }[stage.status];

  const labelColor = {
    pending: "text-gray-400",
    active: "text-blue-700 font-semibold",
    done: "text-green-700",
    error: "text-red-600",
  }[stage.status];

  const icon = stage.status === "done" ? "✓" : stage.status === "error" ? "✗" : null;

  return (
    <div className={`border-2 rounded-lg px-3 py-2.5 w-28 ${border}`}>
      <div className="flex items-center gap-1.5 mb-0.5">
        {icon ? (
          <span className={`text-xs font-bold ${stage.status === "done" ? "text-green-600" : "text-red-500"}`}>
            {icon}
          </span>
        ) : (
          <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${dot}`} />
        )}
        <span className={`text-xs ${labelColor}`}>{stage.label}</span>
      </div>
      {stage.detail && (
        <p className="text-xs text-gray-500 pl-3.5">{stage.detail}</p>
      )}
      {stage.status === "error" && (
        <p className="text-xs text-red-400 pl-3.5">blocked</p>
      )}
    </div>
  );
}

// ── State derivation ─────────────────────────────────────────────────────────

function computeStages(events: CycleEvent[], cycleStatus?: string): Stage[] {
  // Seed initial state from persisted Firestore cycle_status
  const s: Record<string, StageStatus> = fromCycleStatus(cycleStatus);
  let researchTotal = 0;
  let researchDone = 0;
  let storyTitle: string | undefined;
  let complianceNote: string | undefined;

  // Replay events chronologically (hook returns newest-first)
  for (const ev of [...events].reverse()) {
    switch (ev.event) {
      case "cycle_start":
        if (s.select === "pending") s.select = "active";
        // Reset research counters for this fresh cycle
        researchTotal = 0;
        researchDone = 0;
        break;
      case "story_selected":
        s.select = "done";
        storyTitle = (ev.data.story_title as string | undefined)?.slice(0, 28);
        if (s.decompose === "pending") s.decompose = "active";
        break;
      case "mandate_decomposed":
        s.decompose = "done";
        if (s.research === "pending") s.research = "active";
        break;
      case "researchers_spawned":
        s.research = "active";
        researchTotal = (ev.data.count as number) || researchTotal;
        break;
      case "evidence_stored":
        if (s.research !== "done") {
          researchDone = Math.min(researchDone + 1, researchTotal || 999);
        }
        break;
      case "research_complete":
        s.research = "done";
        if (s.compliance === "pending") s.compliance = "active";
        break;
      case "compliance_result":
        s.compliance = (ev.data.passed as boolean) ? "done" : "error";
        if (!ev.data.passed) complianceNote = "drift or injection";
        if (ev.data.passed && s.legal_tree === "pending") s.legal_tree = "active";
        break;
      case "building_legal_tree":
        if (s.research === "active") s.research = "done";
        if (s.compliance === "pending" || s.compliance === "active") s.compliance = "done";
        s.legal_tree = "active";
        break;
      case "legal_tree_ready":
        s.legal_tree = "done";
        if (s.publish === "pending") s.publish = "active";
        break;
      case "story_published":
        s.publish = "done";
        break;
      case "cycle_complete":
        for (const k of STAGE_ORDER) {
          if (s[k] === "active") s[k] = "done";
        }
        break;
      case "cycle_error":
        for (const k of STAGE_ORDER) {
          if (s[k] === "active") s[k] = "error";
        }
        break;
    }
  }

  const researchDetail =
    s.research === "done"
      ? researchTotal > 0 ? `${researchTotal} done` : undefined
      : researchTotal > 0
      ? `${researchDone}/${researchTotal}`
      : s.research === "active"
      ? "searching…"
      : undefined;

  return [
    { id: "select",      label: "Select Story", status: s.select,      detail: s.select === "done" ? storyTitle : undefined },
    { id: "decompose",   label: "Decompose",    status: s.decompose },
    { id: "research",    label: "Research",     status: s.research,    detail: researchDetail },
    { id: "compliance",  label: "Compliance",   status: s.compliance,  detail: s.compliance === "error" ? complianceNote : undefined },
    { id: "legal_tree",  label: "Legal Tree",   status: s.legal_tree },
    { id: "publish",     label: "Publish",      status: s.publish },
  ];
}

function fromCycleStatus(status?: string): Record<string, StageStatus> {
  const all: Record<string, StageStatus> = Object.fromEntries(
    STAGE_ORDER.map((k) => [k, "pending" as StageStatus]),
  );
  const done = (keys: string[]): Record<string, StageStatus> =>
    Object.fromEntries(STAGE_ORDER.map((k) => [k, keys.includes(k) ? "done" : "pending"]));

  switch (status) {
    case "story_selected":
      return { ...all, select: "done", decompose: "active" };
    case "researching":
      return { ...done(["select", "decompose"]), research: "active", compliance: "pending", legal_tree: "pending", publish: "pending" };
    case "building_legal_tree":
      return { ...done(["select", "decompose", "research", "compliance"]), legal_tree: "active", publish: "pending" };
    case "publishing":
      return { ...done(["select", "decompose", "research", "compliance", "legal_tree"]), publish: "active" };
    default:
      return all;
  }
}
