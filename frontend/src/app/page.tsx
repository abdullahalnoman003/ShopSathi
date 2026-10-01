"use client";

import { useEffect, useState } from "react";
import { ApiError, getHealth, type HealthStatus } from "@/lib/api/client";

// Placeholder only: proves frontend <-> backend integration. Later prompts replace it.
export default function Home() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-4 py-10">
      <div>
        <h1 className="text-3xl font-bold">ShopSathi</h1>
        <p className="mt-1 text-sm opacity-70">AI sales agent for small online shops</p>
      </div>
      <section className="rounded-lg border border-black/15 p-4 dark:border-white/20">
        <h2 className="mb-3 font-semibold">Backend status</h2>
        {error && <p className="text-red-600">{error}</p>}
        {!error && !health && <p>Checking…</p>}
        {health && (
          <ul className="space-y-1">
            {(["api", "database", "redis"] as const).map((k) => (
              <li key={k} className="flex justify-between">
                <span className="capitalize">{k}</span>
                <span className={health[k] === "ok" ? "text-green-600" : "text-red-600"}>{health[k]}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
