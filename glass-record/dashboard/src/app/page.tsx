"use client";

import { useEffect, useState } from "react";
import { getAllJournalists } from "@/lib/firebase";

const JURISDICTIONS = ["UN", "EU", "ICC", "ICJ", "US_FEDERAL", "NATO", "WORLD_BANK", "ECHR"];
const EDITOR_URL = process.env.NEXT_PUBLIC_EDITOR_URL ?? "http://localhost:8000";

interface Journalist {
  id: string;
  mandate: string;
  jurisdiction: string;
  tier: string;
  created_at: string;
}

interface SpawnForm {
  mandate: string;
  jurisdiction: string;
  schedule: string;
}

export default function HomePage() {
  const [journalists, setJournalists] = useState<Journalist[]>([]);
  const [loading, setLoading] = useState(true);
  const [showSpawn, setShowSpawn] = useState(false);
  const [form, setForm] = useState<SpawnForm>({
    mandate: "",
    jurisdiction: "UN",
    schedule: "0 6 * * *",
  });
  const [spawning, setSpawning] = useState(false);
  const [spawnError, setSpawnError] = useState<string | null>(null);

  useEffect(() => {
    getAllJournalists().then((data) => {
      setJournalists(data as Journalist[]);
      setLoading(false);
      // Auto-open spawn form if no journalists yet
      if (data.length === 0) setShowSpawn(true);
    });
  }, []);

  async function handleSpawn(e: React.FormEvent) {
    e.preventDefault();
    if (form.mandate.trim().length < 20) {
      setSpawnError("Mandate must be at least 20 characters.");
      return;
    }
    setSpawnError(null);
    setSpawning(true);
    try {
      const res = await fetch(`${EDITOR_URL}/spawn`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mandate: form.mandate.trim(),
          jurisdiction: form.jurisdiction,
          schedule: form.schedule.trim() || "0 6 * * *",
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      window.location.href = `/${data.journalist_id}`;
    } catch (err) {
      setSpawnError((err as Error).message);
      setSpawning(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold mb-1">Active Journalists</h1>
          <p className="text-gray-500 text-sm">
            Each journalist is an autonomous agent with an immutable mandate.
            Every action, source, and reasoning step is public.
          </p>
        </div>
        <button
          onClick={() => { setShowSpawn(!showSpawn); setSpawnError(null); }}
          className="shrink-0 ml-4 px-4 py-2 text-xs bg-gray-900 text-white rounded hover:bg-gray-700 transition-colors"
        >
          {showSpawn ? "Cancel" : "+ Spawn journalist"}
        </button>
      </div>

      {/* Spawn form */}
      {showSpawn && (
        <div className="border-2 border-gray-900 rounded-lg p-6 mb-8 bg-gray-50">
          <h2 className="text-sm font-bold mb-4 uppercase tracking-widest">Spawn a new journalist</h2>
          <form onSubmit={handleSpawn} className="space-y-5">
            {/* Mandate */}
            <div>
              <label className="block text-xs text-gray-500 mb-1.5 uppercase tracking-widest">
                Mandate <span className="text-gray-400 normal-case tracking-normal">(immutable — set once, never changed)</span>
              </label>
              <textarea
                value={form.mandate}
                onChange={(e) => setForm({ ...form, mandate: e.target.value })}
                placeholder="Investigate human rights implications of UN Security Council veto use since 2022, with particular focus on resolutions blocked relating to civilian protection obligations under international humanitarian law."
                rows={4}
                required
                minLength={20}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:border-gray-900"
              />
              <p className={`text-xs mt-1 ${form.mandate.length < 20 ? "text-red-400" : "text-gray-400"}`}>
                {form.mandate.length} chars {form.mandate.length < 20 ? `— need ${20 - form.mandate.length} more` : "✓"}
              </p>
            </div>

            {/* Jurisdiction + Schedule */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1.5 uppercase tracking-widest">Jurisdiction</label>
                <select
                  value={form.jurisdiction}
                  onChange={(e) => setForm({ ...form, jurisdiction: e.target.value })}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-gray-900"
                >
                  {JURISDICTIONS.map((j) => (
                    <option key={j} value={j}>{j}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5 uppercase tracking-widest">
                  Schedule <span className="text-gray-400 normal-case tracking-normal">(UTC cron)</span>
                </label>
                <input
                  type="text"
                  value={form.schedule}
                  onChange={(e) => setForm({ ...form, schedule: e.target.value })}
                  placeholder="0 6 * * *"
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-gray-900"
                />
                <p className="text-xs text-gray-400 mt-1">
                  {form.schedule === "0 6 * * *" ? "Daily at 06:00 UTC" : "Custom schedule"}
                </p>
              </div>
            </div>

            {spawnError && (
              <p className="text-xs text-red-600 border border-red-200 rounded px-3 py-2 bg-red-50">
                {spawnError}
              </p>
            )}

            <button
              type="submit"
              disabled={spawning || form.mandate.trim().length < 20}
              className="px-5 py-2.5 bg-gray-900 text-white text-sm rounded hover:bg-gray-700 disabled:opacity-40 transition-colors"
            >
              {spawning ? "Spawning…" : "Spawn journalist →"}
            </button>
          </form>
        </div>
      )}

      {/* Journalist list */}
      {loading && <p className="text-gray-400 text-sm animate-pulse">Loading…</p>}

      <div className="space-y-3">
        {journalists.map((j) => (
          <a
            key={j.id}
            href={`/${j.id}`}
            className="block border border-gray-200 rounded-lg p-5 hover:border-gray-400 transition-colors group"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <span className="text-xs text-gray-400 uppercase tracking-widest">
                  {j.jurisdiction} · {j.tier}
                </span>
                <p className="mt-1 text-sm font-medium leading-snug">{j.mandate}</p>
              </div>
              <span className="text-xs text-gray-300 ml-4 shrink-0 group-hover:text-gray-400 transition-colors">
                {j.id} →
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-3">
              Spawned {new Date(j.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
            </p>
          </a>
        ))}

        {!loading && journalists.length === 0 && !showSpawn && (
          <p className="text-gray-400 text-sm">
            No journalists spawned yet. Use the button above to create the first one.
          </p>
        )}
      </div>
    </div>
  );
}
