"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { use } from "react";
import dynamic from "next/dynamic";
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
import { PipelineDiagram } from "@/components/PipelineDiagram";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => <p className="text-gray-400 text-sm">Loading graph engine…</p>,
});

type Tab =
  | "mandate"
  | "pipeline"
  | "investigation"
  | "activity"
  | "evidence"
  | "graph"
  | "compliance"
  | "stories"
  | "cost"
  | "tips";

interface GraphNode { id: string; label: string; group: number; x?: number; y?: number }
interface GraphLink { source: string; target: string; label: string }
interface GraphData { nodes: GraphNode[]; links: GraphLink[] }

const NODE_COLORS: Record<number, string> = {
  0: "#111827",
  1: "#3b82f6",
  2: "#10b981",
  3: "#f59e0b",
};

// ── Small shared UI components ───────────────────────────────────────────────

function TabBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 text-xs uppercase tracking-widest border-b-2 transition-colors ${
        active ? "border-gray-900 text-gray-900" : "border-transparent text-gray-400 hover:text-gray-600"
      }`}
    >
      {label}
    </button>
  );
}

function Badge({ value }: { value: number }) {
  const color = value > 0.7 ? "bg-green-500" : value > 0.4 ? "bg-yellow-400" : "bg-red-400";
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

// ── Investigation tab helpers ────────────────────────────────────────────────

function groupBySubQuestion(items: Record<string, unknown>[]) {
  const map = new Map<string, Record<string, unknown>[]>();
  for (const item of items) {
    const q = (item.sub_question as string) || "General findings";
    if (!map.has(q)) map.set(q, []);
    map.get(q)!.push(item);
  }
  return map;
}

function topEntities(items: Record<string, unknown>[]) {
  const freq = new Map<string, { name: string; type: string; count: number }>();
  for (const item of items) {
    for (const e of (item.entities as { name: string; type: string }[]) || []) {
      const key = e.name.toLowerCase();
      if (freq.has(key)) freq.get(key)!.count++;
      else freq.set(key, { ...e, count: 1 });
    }
  }
  return [...freq.values()].sort((a, b) => b.count - a.count).slice(0, 20);
}

// ── Story modal ──────────────────────────────────────────────────────────────

function StoryModal({ story, onClose }: { story: Record<string, unknown>; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-white">
      <div className="max-w-3xl mx-auto px-6 py-10">
        <button onClick={onClose} className="text-xs text-gray-400 hover:text-gray-700 mb-6 inline-block">
          ← Back
        </button>
        <p className="text-xs text-gray-400 uppercase tracking-widest mb-2">{story.published_at as string}</p>
        <h1 className="text-2xl font-bold leading-tight mb-3">{story.title as string}</h1>
        <p className="text-base text-gray-600 mb-6 leading-relaxed">{story.standfirst as string}</p>
        <div className="flex gap-2 mb-8 flex-wrap">
          {(story.tags as string[])?.map((tag) => (
            <span key={tag} className="text-xs bg-gray-100 px-2 py-0.5 rounded">{tag}</span>
          ))}
        </div>
        <div
          className="prose prose-sm max-w-none text-gray-800"
          dangerouslySetInnerHTML={{ __html: story.body_html as string }}
        />
      </div>
    </div>
  );
}

// ── Graph node detail panel ──────────────────────────────────────────────────

function NodeDetail({
  node,
  journalist,
  evidence,
  stories,
  onClose,
  onReadStory,
}: {
  node: GraphNode;
  journalist: Record<string, unknown>;
  evidence: Record<string, unknown>[];
  stories: Record<string, unknown>[];
  onClose: () => void;
  onReadStory: (s: Record<string, unknown>) => void;
}) {
  // Evidence node
  if (node.group === 2) {
    const evidenceId = node.id.slice(2); // strip "e-"
    const item = evidence.find((e) => e.evidence_id === evidenceId);
    if (!item) return null;
    return (
      <div className="border border-gray-200 rounded-lg p-4 mt-4 relative">
        <button onClick={onClose} className="absolute top-3 right-3 text-gray-300 hover:text-gray-600 text-xs">✕</button>
        <div className="flex items-start gap-2 mb-2">
          <Badge value={item.credibility_score as number} />
          <a href={item.source_url as string} target="_blank" rel="noopener noreferrer"
            className="text-sm font-medium underline leading-tight">
            {item.source_title as string}
          </a>
        </div>
        <p className="text-xs text-gray-400 mb-2">{item.sub_question as string}</p>
        {(item.claims as string[])?.length > 0 && (
          <ul className="space-y-1 mb-3">
            {(item.claims as string[]).map((claim, i) => (
              <li key={i} className="text-xs text-gray-700">· {claim}</li>
            ))}
          </ul>
        )}
        {(item.entities as { name: string; type: string }[])?.length > 0 && (
          <div className="flex gap-1 flex-wrap">
            {(item.entities as { name: string; type: string }[]).map((e, i) => (
              <span key={i} className="text-xs bg-gray-50 border border-gray-100 px-2 py-0.5 rounded">
                {e.name} <span className="text-gray-300">·{e.type}</span>
              </span>
            ))}
          </div>
        )}
        <p className="text-xs text-gray-300 mt-2">
          Credibility: {(item.credibility_score as number).toFixed(2)} — {item.credibility_notes as string}
        </p>
      </div>
    );
  }

  // Entity node
  if (node.group === 3) {
    const entityName = node.label;
    const related = evidence.filter((e) =>
      (e.entities as { name: string }[])?.some(
        (ent) => ent.name.toLowerCase() === entityName.toLowerCase(),
      ),
    );
    return (
      <div className="border border-gray-200 rounded-lg p-4 mt-4 relative">
        <button onClick={onClose} className="absolute top-3 right-3 text-gray-300 hover:text-gray-600 text-xs">✕</button>
        <p className="text-xs text-gray-400 uppercase tracking-widest mb-1">Entity</p>
        <h3 className="text-sm font-semibold mb-3">{entityName}</h3>
        <p className="text-xs text-gray-500 mb-3">Appears in {related.length} evidence item{related.length !== 1 ? "s" : ""}:</p>
        <div className="space-y-2">
          {related.map((item) => (
            <div key={item.evidence_id as string} className="border border-gray-100 rounded px-3 py-2">
              <a href={item.source_url as string} target="_blank" rel="noopener noreferrer"
                className="text-xs underline text-blue-600">{item.source_title as string}</a>
              <p className="text-xs text-gray-400 mt-0.5">{item.sub_question as string}</p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Story node
  if (node.group === 1) {
    const storyId = node.id.slice(2); // strip "s-"
    const story = stories.find((s) => s.story_id === storyId);
    if (!story) return null;
    return (
      <div className="border border-gray-200 rounded-lg p-4 mt-4 relative">
        <button onClick={onClose} className="absolute top-3 right-3 text-gray-300 hover:text-gray-600 text-xs">✕</button>
        <p className="text-xs text-gray-400 mb-1">{story.published_at as string}</p>
        <h3 className="text-sm font-semibold mb-2">{story.title as string}</h3>
        <p className="text-xs text-gray-500 mb-3">{story.standfirst as string}</p>
        <button onClick={() => onReadStory(story)} className="text-xs underline text-blue-600">
          Read full article →
        </button>
      </div>
    );
  }

  // Journalist node
  if (node.group === 0) {
    return (
      <div className="border border-gray-200 rounded-lg p-4 mt-4 relative">
        <button onClick={onClose} className="absolute top-3 right-3 text-gray-300 hover:text-gray-600 text-xs">✕</button>
        <p className="text-xs text-gray-400 uppercase tracking-widest mb-1">Journalist</p>
        <p className="text-xs text-gray-500">{journalist.jurisdiction as string} · {journalist.tier as string}</p>
        <p className="text-sm mt-2 leading-relaxed">{journalist.mandate as string}</p>
      </div>
    );
  }

  return null;
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function JournalistPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [journalist, setJournalist] = useState<Record<string, unknown> | null>(null);
  const [activity, setActivity] = useState<Record<string, unknown>[]>([]);
  const [evidence, setEvidence] = useState<Record<string, unknown>[]>([]);
  const [compliance, setCompliance] = useState<Record<string, unknown>[]>([]);
  const [stories, setStories] = useState<Record<string, unknown>[]>([]);
  const [costs, setCosts] = useState<Record<string, unknown>[]>([]);
  const [tips, setTips] = useState<Record<string, unknown>[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>("pipeline");
  const [tipText, setTipText] = useState("");
  const [tipSubmitting, setTipSubmitting] = useState(false);
  const [tipSent, setTipSent] = useState(false);
  const [openStory, setOpenStory] = useState<Record<string, unknown> | null>(null);

  // Run now
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  // Knowledge graph
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const graphContainerRef = useRef<HTMLDivElement>(null);
  const [graphDims, setGraphDims] = useState({ width: 800, height: 500 });

  const { events: sseEvents, status: sseStatus, connected } = useSSE(slug);
  const EDITOR_URL = process.env.NEXT_PUBLIC_EDITOR_URL ?? "http://localhost:8000";

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

  useEffect(() => {
    if (activeTab !== "graph") return;
    setGraphLoading(true);
    setGraphError(null);
    setSelectedNode(null);
    fetch(`${EDITOR_URL}/graph/${slug}`)
      .then((r) => { if (!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); })
      .then((data: GraphData) => setGraphData(data))
      .catch((e: Error) => setGraphError(e.message))
      .finally(() => setGraphLoading(false));
  }, [activeTab, slug, EDITOR_URL]);

  useEffect(() => {
    if (!graphContainerRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const { width } = entries[0].contentRect;
      setGraphDims({ width, height: Math.max(400, width * 0.6) });
    });
    obs.observe(graphContainerRef.current);
    return () => obs.disconnect();
  }, [activeTab]);

  const nodeCanvasObject = useCallback(
    (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isSelected = selectedNode?.id === node.id;
      const r = Math.max(4, (isSelected ? 8 : 6) / globalScale);
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
      ctx.fillStyle = NODE_COLORS[node.group] ?? "#6b7280";
      ctx.fill();
      if (isSelected) {
        ctx.strokeStyle = "#1d4ed8";
        ctx.lineWidth = 2 / globalScale;
        ctx.stroke();
      }
      const fontSize = Math.max(8, 10 / globalScale);
      ctx.font = `${fontSize}px monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#374151";
      ctx.fillText(
        node.label.length > 20 ? node.label.slice(0, 18) + "…" : node.label,
        node.x ?? 0,
        (node.y ?? 0) + r + fontSize,
      );
    },
    [selectedNode],
  );

  const totalCostUsd = costs.reduce((sum, c) => sum + ((c.cost_usd as number) ?? 0), 0);

  async function runNow() {
    if (!journalist) return;
    setRunning(true);
    setRunError(null);
    try {
      const res = await fetch(`${EDITOR_URL}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          journalist_id: slug,
          mandate: journalist.mandate,
          jurisdiction: journalist.jurisdiction,
          tier: journalist.tier ?? "free",
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `${res.status} ${res.statusText}`);
      }
      setActiveTab("pipeline");
    } catch (err) {
      setRunError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

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
    return <div className="max-w-4xl mx-auto px-6 py-12 text-gray-400 text-sm animate-pulse">Loading…</div>;
  }

  const cycleStatus = (journalist.cycle_status as Record<string, unknown> | undefined)?.status as string | undefined;

  const tabs: [Tab, string][] = [
    ["pipeline",     "Pipeline"],
    ["mandate",      "Mandate"],
    ["investigation","Investigation"],
    ["activity",     `Activity (${activity.length})`],
    ["evidence",     `Evidence (${evidence.length})`],
    ["graph",        "Knowledge Graph"],
    ["compliance",   `Compliance (${compliance.length})`],
    ["stories",      `Stories (${stories.length})`],
    ["cost",         `Cost ($${totalCostUsd.toFixed(4)})`],
    ["tips",         `Tips (${tips.length})`],
  ];

  const byQuestion = groupBySubQuestion(evidence);
  const entities = topEntities(evidence);

  return (
    <>
      {openStory && <StoryModal story={openStory} onClose={() => setOpenStory(null)} />}

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1 min-w-0">
            <span className="text-xs text-gray-400 uppercase tracking-widest">
              {journalist.jurisdiction as string} · {journalist.tier as string}
            </span>
            <h1 className="text-xl font-bold mt-1 leading-snug">{journalist.mandate as string}</h1>
            <p className="text-xs text-gray-400 mt-1">ID: {slug}</p>
          </div>
          <div className="ml-4 shrink-0 flex flex-col items-end gap-2">
            <button
              onClick={runNow}
              disabled={running}
              className="px-3 py-1.5 text-xs bg-gray-900 text-white rounded hover:bg-gray-700 disabled:opacity-40 transition-colors"
            >
              {running ? "Starting…" : "▶ Run now"}
            </button>
            {runError && <p className="text-xs text-red-500 max-w-xs text-right">{runError}</p>}
          </div>
        </div>

        {/* Live status bar */}
        <div className="flex items-center gap-3 mb-5 text-xs">
          <span className={`inline-block w-2 h-2 rounded-full ${
            connected
              ? cycleStatus === "idle" || !cycleStatus ? "bg-gray-300" : "bg-green-400 animate-pulse"
              : "bg-gray-200"
          }`} />
          <span className="text-gray-500">{connected ? sseStatus : "Connecting…"}</span>
          <span className="text-gray-300 ml-auto">Total spend: ${totalCostUsd.toFixed(4)}</span>
        </div>

        {/* Tabs */}
        <div className="flex gap-0 border-b border-gray-100 mb-8 flex-wrap">
          {tabs.map(([id, label]) => (
            <TabBtn key={id} label={label} active={activeTab === id} onClick={() => setActiveTab(id)} />
          ))}
        </div>

        {/* ── Pipeline ────────────────────────────────────────────────────── */}
        {activeTab === "pipeline" && (
          <div className="space-y-8">
            <Section title="Cycle state machine">
              <PipelineDiagram events={sseEvents} cycleStatus={cycleStatus} />
            </Section>

            <Section title={`Live events${sseEvents.length ? ` (${sseEvents.length})` : ""}`}>
              <p className="text-xs text-gray-400 mb-3">
                Real-time events from the Editor agent. Resets each page session.
              </p>
              {sseEvents.length === 0 && (
                <Empty text={connected ? "Waiting for next cycle…" : "Connecting to live stream…"} />
              )}
              <div className="space-y-1.5">
                {sseEvents.map((ev, i) => (
                  <div key={i} className="border border-gray-100 rounded px-3 py-2 text-xs font-mono">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-gray-700">{ev.event}</span>
                      <span className="text-gray-300">{ev.ts}</span>
                    </div>
                    <pre className="text-gray-400 whitespace-pre-wrap overflow-x-auto text-xs">
                      {JSON.stringify(ev.data, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </Section>
          </div>
        )}

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
                {journalist.created_at ? new Date(journalist.created_at as string).toUTCString() : "—"}
              </p>
            </Section>
            {journalist.cycle_status && (
              <Section title="Cycle status">
                <pre className="text-xs text-gray-500 whitespace-pre-wrap">
                  {JSON.stringify(journalist.cycle_status, null, 2)}
                </pre>
              </Section>
            )}
          </div>
        )}

        {/* ── Investigation ────────────────────────────────────────────────── */}
        {activeTab === "investigation" && (
          <div className="space-y-8">
            {evidence.length === 0 && <Empty text="No investigation data yet — run a cycle first." />}

            {byQuestion.size > 0 && (
              <Section title={`Research questions (${byQuestion.size})`}>
                <div className="space-y-5 mt-2">
                  {[...byQuestion.entries()].map(([question, items]) => (
                    <div key={question} className="border border-gray-100 rounded p-4">
                      <p className="text-sm font-medium text-gray-800 mb-3">❓ {question}</p>
                      <div className="space-y-3">
                        {items.map((item) => (
                          <div key={item.evidence_id as string}>
                            <div className="flex items-start gap-2">
                              <Badge value={item.credibility_score as number} />
                              <a href={item.source_url as string} target="_blank" rel="noopener noreferrer"
                                className="text-xs text-blue-600 underline truncate max-w-sm">
                                {item.source_title as string}
                              </a>
                            </div>
                            {(item.claims as string[])?.length > 0 && (
                              <ul className="mt-1 ml-4 space-y-0.5">
                                {(item.claims as string[]).map((claim, i) => (
                                  <li key={i} className="text-xs text-gray-600">· {claim}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {entities.length > 0 && (
              <Section title="Who and what keeps coming up">
                <p className="text-xs text-gray-400 mb-3">
                  Entities appearing across multiple sources.
                </p>
                <div className="flex flex-wrap gap-2">
                  {entities.map((e) => (
                    <span key={e.name}
                      className="inline-flex items-center gap-1.5 text-xs border border-gray-200 rounded px-2 py-1">
                      <span>{e.name}</span>
                      <span className="text-gray-300">·{e.type}</span>
                      {e.count > 1 && (
                        <span className="bg-gray-100 text-gray-500 rounded-full px-1.5">×{e.count}</span>
                      )}
                    </span>
                  ))}
                </div>
              </Section>
            )}

            {stories.length > 0 && (
              <Section title="Latest published article">
                {stories.slice(0, 1).map((story) => (
                  <div key={story.story_id as string} className="border border-gray-200 rounded p-4">
                    <p className="text-xs text-gray-400 mb-1">{story.published_at as string}</p>
                    <h3 className="text-sm font-semibold mb-1">{story.title as string}</h3>
                    <p className="text-xs text-gray-500 mb-3">{story.standfirst as string}</p>
                    <button onClick={() => setOpenStory(story)} className="text-xs underline text-blue-600">
                      Read full article →
                    </button>
                  </div>
                ))}
              </Section>
            )}
          </div>
        )}

        {/* ── Activity Log ──────────────────────────────────────────────────── */}
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

        {/* ── Evidence Locker ───────────────────────────────────────────────── */}
        {activeTab === "evidence" && (
          <div className="space-y-3">
            {evidence.length === 0 && <Empty text="No evidence collected yet." />}
            {evidence.map((item) => (
              <div key={item.evidence_id as string} className="border border-gray-100 rounded px-4 py-3">
                <div className="flex items-start justify-between">
                  <div>
                    <Badge value={item.credibility_score as number} />
                    <a href={item.source_url as string} target="_blank" rel="noopener noreferrer"
                      className="text-sm font-medium underline">
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
                {(item.entities as { name: string; type: string }[])?.length > 0 && (
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {(item.entities as { name: string; type: string }[]).map((e, i) => (
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

        {/* ── Knowledge Graph ───────────────────────────────────────────────── */}
        {activeTab === "graph" && (
          <div>
            {/* Legend + hint */}
            <div className="flex flex-wrap items-center gap-4 mb-3 text-xs text-gray-500">
              {([["Journalist", 0], ["Story", 1], ["Evidence", 2], ["Entity", 3]] as [string, number][]).map(
                ([label, group]) => (
                  <span key={label} className="flex items-center gap-1.5">
                    <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: NODE_COLORS[group] }} />
                    {label}
                  </span>
                ),
              )}
              <span className="ml-auto text-gray-300">Click a node to inspect</span>
            </div>

            {graphLoading && <p className="text-gray-400 text-sm">Building graph from evidence…</p>}
            {graphError && <p className="text-red-400 text-sm">Error: {graphError}</p>}
            {!graphLoading && !graphError && graphData.nodes.length === 0 && (
              <Empty text="No graph data yet — run an investigation cycle first." />
            )}

            {!graphLoading && !graphError && graphData.nodes.length > 0 && (
              <div
                ref={graphContainerRef}
                className="border border-gray-100 rounded overflow-hidden bg-gray-50 cursor-pointer"
                style={{ height: graphDims.height }}
              >
                <ForceGraph2D
                  graphData={graphData}
                  width={graphDims.width}
                  height={graphDims.height}
                  backgroundColor="#f9fafb"
                  linkLabel="label"
                  linkColor={() => "#d1d5db"}
                  linkDirectionalArrowLength={4}
                  linkDirectionalArrowRelPos={1}
                  nodeCanvasObject={nodeCanvasObject as Parameters<typeof ForceGraph2D>[0]["nodeCanvasObject"]}
                  nodePointerAreaPaint={(node: GraphNode, color, ctx) => {
                    ctx.fillStyle = color;
                    ctx.beginPath();
                    ctx.arc(node.x ?? 0, node.y ?? 0, 10, 0, 2 * Math.PI);
                    ctx.fill();
                  }}
                  onNodeClick={(node) => setSelectedNode(node as GraphNode)}
                  enableNodeDrag
                  cooldownTicks={80}
                />
              </div>
            )}

            {!graphLoading && (
              <p className="text-xs text-gray-300 mt-1.5">
                {graphData.nodes.length} nodes · {graphData.links.length} relationships
              </p>
            )}

            {/* Node detail panel */}
            {selectedNode && (
              <NodeDetail
                node={selectedNode}
                journalist={journalist}
                evidence={evidence}
                stories={stories}
                onClose={() => setSelectedNode(null)}
                onReadStory={(s) => { setOpenStory(s); setSelectedNode(null); }}
              />
            )}
          </div>
        )}

        {/* ── Compliance Log ────────────────────────────────────────────────── */}
        {activeTab === "compliance" && (
          <div className="space-y-3">
            {compliance.length === 0 && <Empty text="No compliance checks yet." />}
            {compliance.map((entry) => (
              <div key={entry.id as string}
                className={`border rounded px-4 py-3 text-xs ${entry.passed ? "border-green-200" : "border-red-200"}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className={`font-medium ${entry.passed ? "text-green-700" : "text-red-600"}`}>
                    {entry.passed ? "PASSED" : "FAILED"} — {entry.check_type as string}
                  </span>
                  <span className="text-gray-300">{entry.cycle_id as string}</span>
                </div>
                <p className="text-gray-600">{entry.reasoning as string}</p>
                {(entry.drift_flags as string[])?.length > 0 && (
                  <ul className="mt-2 space-y-1 text-red-500">
                    {(entry.drift_flags as string[]).map((f, i) => <li key={i}>⚠ {f}</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}

        {/* ── Stories ───────────────────────────────────────────────────────── */}
        {activeTab === "stories" && (
          <div className="space-y-4">
            {stories.length === 0 && <Empty text="No stories published yet." />}
            {stories.map((story) => (
              <div key={story.story_id as string} className="border border-gray-200 rounded px-5 py-4">
                <p className="text-xs text-gray-400 mb-1">{story.published_at as string}</p>
                <h3 className="text-sm font-semibold mb-1">{story.title as string}</h3>
                <p className="text-xs text-gray-500 mb-3">{story.standfirst as string}</p>
                <div className="flex gap-2 mb-3 flex-wrap">
                  {(story.tags as string[])?.map((tag) => (
                    <span key={tag} className="text-xs bg-gray-100 px-2 py-0.5 rounded">{tag}</span>
                  ))}
                </div>
                <button onClick={() => setOpenStory(story)} className="text-xs underline text-blue-600">
                  Read full article →
                </button>
              </div>
            ))}
          </div>
        )}

        {/* ── Cost Ledger ───────────────────────────────────────────────────── */}
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

        {/* ── Tips ──────────────────────────────────────────────────────────── */}
        {activeTab === "tips" && (
          <div className="space-y-6">
            <Section title="Submit a tip or correction">
              <p className="text-xs text-gray-400 mb-3">
                Tips are cross-checked against the evidence locker. Zero editorial influence. All public.
              </p>
              {tipSent ? (
                <p className="text-green-600 text-sm">Tip received. The Verification Agent will assess it.</p>
              ) : (
                <form onSubmit={submitTip} className="space-y-3">
                  <textarea value={tipText} onChange={(e) => setTipText(e.target.value)}
                    placeholder="Describe the tip, correction, or additional evidence…"
                    rows={4}
                    className="w-full border border-gray-200 rounded px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:border-gray-400"
                  />
                  <button type="submit" disabled={tipSubmitting || !tipText.trim()}
                    className="px-4 py-2 text-xs bg-gray-900 text-white rounded disabled:opacity-40">
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
      </div>
    </>
  );
}
