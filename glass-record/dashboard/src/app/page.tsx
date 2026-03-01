"use client";

import { useEffect, useState } from "react";
import { getAllJournalists } from "@/lib/firebase";

interface Journalist {
  id: string;
  mandate: string;
  jurisdiction: string;
  tier: string;
  created_at: string;
}

export default function HomePage() {
  const [journalists, setJournalists] = useState<Journalist[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAllJournalists().then((data) => {
      setJournalists(data as Journalist[]);
      setLoading(false);
    });
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      <h1 className="text-3xl font-bold mb-2">Active Journalists</h1>
      <p className="text-gray-500 text-sm mb-10">
        Each journalist is an autonomous agent with an immutable mandate.
        Every action is logged publicly below.
      </p>

      {loading && (
        <p className="text-gray-400 text-sm animate-pulse">Loading…</p>
      )}

      <div className="space-y-4">
        {journalists.map((j) => (
          <a
            key={j.id}
            href={`/${j.id}`}
            className="block border border-gray-200 rounded p-5 hover:border-gray-400 transition-colors"
          >
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs text-gray-400 uppercase tracking-widest">
                  {j.jurisdiction} · {j.tier}
                </span>
                <p className="mt-1 text-sm font-medium">{j.mandate}</p>
              </div>
              <span className="text-xs text-gray-300 ml-4 shrink-0">
                {j.id}
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-3">
              Spawned {new Date(j.created_at).toLocaleDateString()}
            </p>
          </a>
        ))}

        {!loading && journalists.length === 0 && (
          <p className="text-gray-400 text-sm">
            No journalists spawned yet.{" "}
            <a href="/spawn" className="underline">
              Spawn the first one.
            </a>
          </p>
        )}
      </div>
    </div>
  );
}
