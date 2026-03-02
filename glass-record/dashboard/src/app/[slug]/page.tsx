"use client";

import { useEffect, useState } from "react";
import { use } from "react";
import {
  subscribeToJournalist,
  subscribeToActivityLog,
  subscribeToEvidenceLocker,
  subscribeToComplianceLog,
  subscribeToStories,
  subscribeToCostLedger,
  subscribeToTips,
} from "@/lib/firebase";
import { useSSE } from "@/lib/useSSE";

type Tab =
  | "mandate"
  | "activity"
  | "evidence"
  | "compliance"
  | "stories"
  | "cost"
  | "tips"
  | "live";

function TabBtn({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 text-xs uppercase tracking-widest border-b-2 transition-colors ${
        active
          ? "border-gray-900 text-gray-900"
          : "border-transparent text-gray-400 hover:text-gray-600"
      }`}
    >
      {label}
    </button>
  );
}

function Badge({ value }: { value: number }) {
  const color =
    value > 0.7 ? "bg-green-500" : value > 0.4 ? "bg-yellow-400" : "bg-red-400";
  return <span className={`inline-block w-2 h-2 rounded-full mr-2 ${color}`} />;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-xs uppercase tracking-widest text-gray-400 mb-2">{title}</h2>
      {children}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-gray-400 text-sm">{text}</p>;
}

export default function JournalistPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const [journalist, setJournalist] = useState<Record<string, unknown> | null>(null);
  const [activity, setActivity] = useState<Record<string, unknown>[]>([]);
  const [evidence, setEvidence] = useState<Record<string, unknown>[]>([]);
  const [compliance, setCompliance] = useState<Record<string, unknown>[]>([]);
  const [stories, setStories] = useState<Record<string, unknown>[]>([]);
  const [costs, setCosts] = useState<Record<string, unknown>[]>([]);
  const [tips, setTips] = useState<Record<string, unknown>[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>("mandate");
  const [tipText, setTipText] = useState("");
  const [tipSubmitting, setTipSubmitting] = useState(false);
  const [tipSent, setTipSent] = useState(false);

  const { events: sseEvents, status: sseStatus, connected } = useSSE(slug);

  useEffect(() => {
    const unsubs = [
      subscribeToJournalist(slug, setJournalist),
      subscribeToActivityLog(slug, setActivity),
      subscribeToEvidenceLocker(slug, setEvidence),
      subscribeToComplianceLog(slug, setCompliance),
      subscribeToStories(slug, setStories),
      subscribeToCostLedger(slug, setCosts),
      subscribeToTips(slug, setTips),
    ];
    return () => unsubs.forEach((u) => u());
  }, [slug]);

  const totalCostUsd = costs.reduce(
    (sum, c) => sum + ((c.cost_usd as number) ?? 0),
    0,
  );

  const EDITOR_URL =
    process.env.NEXT_PUBLIC_EDITOR_URL ?? "http://localhost:8000";

  async function submitTip(e: React.FormEvent) {
    e.preventDefault();
    if (!tipText.trim()) return;
    setTipSubmitting(true);
    try {
      await fetch(`${EDITOR_URL}/tips/${slug}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: tipText.trim() }),
      });
      setTipSent(true);
      setTipText("");
    } finally {
      setTipSubmitting(false);
    }
  }

  if (!journalist) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12 text-gray-400 text-sm animate-pulse">
        Loading journalist…
      </div>
    );
  }

  const tabs: [Tab, string][] = [
    ["mandate", "Mandate"],
    ["activity", `Activity (${activity.length})`],
    ["evidence", `Evidence (${evidence.length})`],
    ["compliance", `Compliance (${compliance.length})`],
    ["stories", `Stories (${stories.length})`],
    ["cost", `Cost ($${totalCostUsd.toFixed(4)})`],
    ["tips", `Tips (${tips.length})`],
    ["live", `Live${sseEvents.length ? ` (${sseEvents.length})` : ""}`],
  ];

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-6">
        <span className="text-xs text-gray-400 uppercase tracking-widest">
          {journalist.jurisdiction as string} · {journalist.tier as string}
        </span>
        <h1 className="text-xl font-bold mt-1 leading-snug">
          {journalist.mandate as string}
        </h1>
        <p className="text-xs text-gray-400 mt-2">ID: {slug}</p>
      </div>

      {/* Live status bar */}
      <div className="flex items-center gap-3 mb-5 text-xs">
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            connected
              ? sseStatus === "Idle" || sseStatus === "idle"
                ? "bg-gray-300"
                : "bg-green-400 animate-pulse"
              : "bg-gray-200"
          }`}
        />
        <span className="text-gray-500">
          {connected ? sseStatus : "Connecting to live stream…"}
        </span>
        <span className="text-gray-300 ml-auto">
          Total spend: ${totalCostUsd.toFixed(4)}
        </span>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-gray-100 mb-8 flex-wrap">
        {tabs.map(([id, label]) => (
          <TabBtn
            key={id}
            label={label}
            active={activeTab === id}
            onClick={() => setActiveTab(id)}
          />
        ))}
      </div>

      {/* ── Mandate ─────────────────────────────────────────────────────── */}
      {activeTab === "mandate" && (
        <div className="space-y-6">
          <Section title="Mandate">
            <p className="text-sm leading-relaxed">{journalist.mandate as string}</p>
            <p className="text-xs text-gray-400 mt-2">Immutable — set at spawn, never modified.</p>
          </Section>
          <Section title="Jurisdiction">
            <p className="text-sm">{journalist.jurisdiction as string}</p>
          </Section>
          <Section title="Spawned">
            <p className="text-sm">
              {journalist.created_at
                ? new Date(journalist.created_at as string).toUTCString()
                : "—"}
            </p>
          </Section>
          {journalist.cycle_status && (
            <Section title="Current cycle status">
              <pre className="text-xs text-gray-500 whitespace-pre-wrap">
                {JSON.stringify(journalist.cycle_status, null, 2)}
              </pre>
            </Section>
          )}
        </div>
      )}

      {/* ── Activity Log ─────────────────────────────────────────────────── */}
      {activeTab === "activity" && (
        <div className="space-y-2">
          {activity.length === 0 && <Empty text="No activity yet." />}
          {activity.map((entry) => (
            <div key={entry.id as string} className="border border-gray-100 rounded px-4 py-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-medium text-gray-700">{entry.action as string}</span>
                <span className="text-gray-300">{entry.timestamp as string}</span>
              </div>
              <pre className="mt-2 text-gray-400 overflow-x-auto whitespace-pre-wrap text-xs">
                {JSON.stringify(entry.data, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}

      {/* ── Evidence Locker ──────────────────────────────────────────────── */}
      {activeTab === "evidence" && (
        <div className="space-y-3">
          {evidence.length === 0 && <Empty text="No evidence collected yet." />}
          {evidence.map((item) => (
            <div key={item.evidence_id as string} className="border border-gray-100 rounded px-4 py-3">
              <div className="flex items-start justify-between">
                <div>
                  <Badge value={item.credibility_score as number} />
                  <a
                    href={item.source_url as string}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium underline"
                  >
                    {item.source_title as string}
                  </a>
                  <p className="text-xs text-gray-400 mt-1">{item.sub_question as string}</p>
                </div>
                <span className="text-xs text-gray-300 ml-4 shrink-0">
                  {(item.credibility_score as number).toFixed(2)}
                </span>
              </div>
              {(item.claims as string[])?.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {(item.claims as string[]).map((claim, i) => (
                    <li key={i} className="text-xs text-gray-600">· {claim}</li>
                  ))}
                </ul>
              )}
              {(item.entities as {name: string; type: string}[])?.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {(item.entities as {name: string; type: string}[]).map((e, i) => (
                    <span key={i} className="text-xs bg-gray-50 border border-gray-100 px-2 py-0.5 rounded">
                      {e.name} <span className="text-gray-300">·{e.type}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Compliance Log ───────────────────────────────────────────────── */}
      {activeTab === "compliance" && (
        <div className="space-y-3">
          {compliance.length === 0 && <Empty text="No compliance checks yet." />}
          {compliance.map((entry) => (
            <div
              key={entry.id as string}
              className={`border rounded px-4 py-3 text-xs ${
                entry.passed ? "border-green-200" : "border-red-200"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className={`font-medium ${entry.passed ? "text-green-700" : "text-red-600"}`}>
                  {entry.passed ? "PASSED" : "FAILED"} — {entry.check_type as string}
                </span>
                <span className="text-gray-300">{entry.cycle_id as string}</span>
              </div>
              <p className="text-gray-600">{entry.reasoning as string}</p>
              {(entry.drift_flags as string[])?.length > 0 && (
                <ul className="mt-2 space-y-1 text-red-500">
                  {(entry.drift_flags as string[]).map((f, i) => (
                    <li key={i}>⚠ {f}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Stories ──────────────────────────────────────────────────────── */}
      {activeTab === "stories" && (
        <div className="space-y-4">
          {stories.length === 0 && <Empty text="No stories published yet." />}
          {stories.map((story) => (
            <div key={story.story_id as string} className="border border-gray-200 rounded px-5 py-4">
              <a
                href={story.ghost_url as string}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium underline"
              >
                {story.title as string}
              </a>
              <p className="text-xs text-gray-400 mt-1">{story.published_at as string}</p>
              <div className="flex gap-2 mt-2 flex-wrap">
                {(story.tags as string[])?.map((tag) => (
                  <span key={tag} className="text-xs bg-gray-100 px-2 py-0.5 rounded">{tag}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Cost Ledger ──────────────────────────────────────────────────── */}
      {activeTab === "cost" && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4 mb-6">
            {([
              ["Total spend", `$${totalCostUsd.toFixed(4)}`],
              ["Cycles", String(costs.length)],
              ["Total tokens", costs.reduce((s, c) => s + ((c.total_tokens as number) ?? 0), 0).toLocaleString()],
            ] as [string, string][]).map(([label, value]) => (
              <div key={label} className="border border-gray-100 rounded p-4">
                <p className="text-xs text-gray-400 mb-1">{label}</p>
                <p className="text-lg font-mono">{value}</p>
              </div>
            ))}
          </div>
          {costs.length === 0 && <Empty text="No cycles run yet." />}
          {costs.map((entry) => (
            <div key={entry.id as string} className="border border-gray-100 rounded px-4 py-3 text-xs font-mono">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-500 truncate mr-4">{entry.cycle_id as string}</span>
                <span className="font-semibold shrink-0">${(entry.cost_usd as number).toFixed(6)}</span>
              </div>
              <div className="grid grid-cols-4 gap-2 text-gray-400">
                <div>calls<br /><span className="text-gray-700">{entry.call_count as number}</span></div>
                <div>in<br /><span className="text-gray-700">{(entry.input_tokens as number).toLocaleString()}</span></div>
                <div>out<br /><span className="text-gray-700">{(entry.output_tokens as number).toLocaleString()}</span></div>
                <div>model<br /><span className="text-gray-700">{(entry.model as string).split("-").slice(-2).join("-")}</span></div>
              </div>
              <p className="text-gray-300 mt-2">{entry.recorded_at as string}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Tips ─────────────────────────────────────────────────────────── */}
      {activeTab === "tips" && (
        <div className="space-y-6">
          <Section title="Submit a tip or correction">
            <p className="text-xs text-gray-400 mb-3">
              Tips are cross-checked against the evidence locker by the Verification Agent.
              They have zero editorial influence. All tips and responses are public.
            </p>
            {tipSent ? (
              <p className="text-green-600 text-sm">
                Tip received. The Verification Agent will assess it against the evidence locker.
              </p>
            ) : (
              <form onSubmit={submitTip} className="space-y-3">
                <textarea
                  value={tipText}
                  onChange={(e) => setTipText(e.target.value)}
                  placeholder="Describe the tip, correction, or additional evidence…"
                  rows={4}
                  className="w-full border border-gray-200 rounded px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:border-gray-400"
                />
                <button
                  type="submit"
                  disabled={tipSubmitting || !tipText.trim()}
                  className="px-4 py-2 text-xs bg-gray-900 text-white rounded disabled:opacity-40"
                >
                  {tipSubmitting ? "Submitting…" : "Submit tip"}
                </button>
              </form>
            )}
          </Section>

          <Section title={`Received tips (${tips.length})`}>
            {tips.length === 0 && <Empty text="No tips submitted yet." />}
            {tips.map((tip) => (
              <div key={tip.id as string} className="border border-gray-100 rounded px-4 py-3 text-xs mb-3">
                <p className="text-gray-700 mb-2">{tip.content as string}</p>
                <p className="text-gray-300">{tip.submitted_at as string}</p>
                {tip.verification && (
                  <div className={`mt-3 pt-3 border-t text-xs ${
                    (tip.verification as Record<string, unknown>).corroborated
                      ? "border-green-100 text-green-700"
                      : "border-gray-100 text-gray-500"
                  }`}>
                    <p className="font-medium mb-1">
                      {(tip.verification as Record<string, unknown>).corroborated
                        ? "Corroborated by evidence"
                        : "Not corroborated"}
                    </p>
                    <p>{(tip.verification as Record<string, unknown>).response as string}</p>
                  </div>
                )}
              </div>
            ))}
          </Section>
        </div>
      )}

      {/* ── Live SSE Feed ────────────────────────────────────────────────── */}
      {activeTab === "live" && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 mb-4">
            Real-time events from the Editor agent — before they land in Firestore.
          </p>
          {sseEvents.length === 0 && (
            <Empty text={connected ? "Waiting for next cycle…" : "Connecting…"} />
          )}
          {sseEvents.map((ev, i) => (
            <div key={i} className="border border-gray-100 rounded px-4 py-3 text-xs font-mono">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-gray-700">{ev.event}</span>
                <span className="text-gray-300">{ev.ts}</span>
              </div>
              <pre className="text-gray-400 whitespace-pre-wrap overflow-x-auto">
                {JSON.stringify(ev.data, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
