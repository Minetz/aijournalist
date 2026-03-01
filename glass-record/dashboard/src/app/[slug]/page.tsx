"use client";

import { useEffect, useState } from "react";
import { use } from "react";
import {
  subscribeToJournalist,
  subscribeToActivityLog,
  subscribeToEvidenceLocker,
  subscribeToComplianceLog,
  subscribeToStories,
} from "@/lib/firebase";

interface TabProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

function Tab({ label, active, onClick }: TabProps) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-xs uppercase tracking-widest border-b-2 transition-colors ${
        active
          ? "border-gray-900 text-gray-900"
          : "border-transparent text-gray-400 hover:text-gray-600"
      }`}
    >
      {label}
    </button>
  );
}

function Badge({ value, max = 1 }: { value: number; max?: number }) {
  const pct = Math.min(value / max, 1);
  const color =
    pct > 0.7 ? "bg-green-500" : pct > 0.4 ? "bg-yellow-400" : "bg-red-400";
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full mr-2 ${color}`}
      title={`${(pct * 100).toFixed(0)}%`}
    />
  );
}

type Tab = "mandate" | "activity" | "evidence" | "compliance" | "stories";

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
  const [activeTab, setActiveTab] = useState<Tab>("mandate");

  useEffect(() => {
    const unsubs = [
      subscribeToJournalist(slug, setJournalist),
      subscribeToActivityLog(slug, setActivity),
      subscribeToEvidenceLocker(slug, setEvidence),
      subscribeToComplianceLog(slug, setCompliance),
      subscribeToStories(slug, setStories),
    ];
    return () => unsubs.forEach((u) => u());
  }, [slug]);

  if (!journalist) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12 text-gray-400 text-sm animate-pulse">
        Loading journalist…
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <span className="text-xs text-gray-400 uppercase tracking-widest">
          {journalist.jurisdiction as string} · {journalist.tier as string}
        </span>
        <h1 className="text-xl font-bold mt-1 leading-snug">
          {journalist.mandate as string}
        </h1>
        <p className="text-xs text-gray-400 mt-2">ID: {slug}</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-100 mb-8">
        {(
          [
            ["mandate", "Mandate"],
            ["activity", `Activity (${activity.length})`],
            ["evidence", `Evidence (${evidence.length})`],
            ["compliance", `Compliance (${compliance.length})`],
            ["stories", `Stories (${stories.length})`],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <Tab
            key={id}
            label={label}
            active={activeTab === id}
            onClick={() => setActiveTab(id)}
          />
        ))}
      </div>

      {/* Mandate */}
      {activeTab === "mandate" && (
        <div className="space-y-6">
          <Section title="Mandate">
            <p className="text-sm leading-relaxed">{journalist.mandate as string}</p>
            <p className="text-xs text-gray-400 mt-2">
              Immutable — set at spawn, never modified.
            </p>
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
        </div>
      )}

      {/* Activity Log */}
      {activeTab === "activity" && (
        <div className="space-y-2">
          {activity.length === 0 && <Empty text="No activity yet." />}
          {activity.map((entry) => (
            <div
              key={entry.id as string}
              className="border border-gray-100 rounded px-4 py-3 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-gray-700">
                  {entry.action as string}
                </span>
                <span className="text-gray-300">{entry.timestamp as string}</span>
              </div>
              <pre className="mt-2 text-gray-400 overflow-x-auto whitespace-pre-wrap text-xs">
                {JSON.stringify(entry.data, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}

      {/* Evidence Locker */}
      {activeTab === "evidence" && (
        <div className="space-y-3">
          {evidence.length === 0 && <Empty text="No evidence collected yet." />}
          {evidence.map((item) => (
            <div
              key={item.evidence_id as string}
              className="border border-gray-100 rounded px-4 py-3"
            >
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
                  <p className="text-xs text-gray-400 mt-1">
                    {item.sub_question as string}
                  </p>
                </div>
                <span className="text-xs text-gray-300 ml-4 shrink-0">
                  {(item.credibility_score as number).toFixed(2)}
                </span>
              </div>
              {(item.claims as string[])?.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {(item.claims as string[]).map((claim, i) => (
                    <li key={i} className="text-xs text-gray-600">
                      · {claim}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Compliance Log */}
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
                <span
                  className={`font-medium ${
                    entry.passed ? "text-green-700" : "text-red-600"
                  }`}
                >
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

      {/* Published Stories */}
      {activeTab === "stories" && (
        <div className="space-y-4">
          {stories.length === 0 && <Empty text="No stories published yet." />}
          {stories.map((story) => (
            <div
              key={story.story_id as string}
              className="border border-gray-200 rounded px-5 py-4"
            >
              <a
                href={story.ghost_url as string}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium underline"
              >
                {story.title as string}
              </a>
              <p className="text-xs text-gray-400 mt-1">
                Published {story.published_at as string}
              </p>
              <div className="flex gap-2 mt-2 flex-wrap">
                {(story.tags as string[])?.map((tag) => (
                  <span
                    key={tag}
                    className="text-xs bg-gray-100 px-2 py-0.5 rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h2 className="text-xs uppercase tracking-widest text-gray-400 mb-2">
        {title}
      </h2>
      {children}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-gray-400 text-sm">{text}</p>;
}
