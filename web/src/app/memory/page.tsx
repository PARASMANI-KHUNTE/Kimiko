"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getFacts, type Fact } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Spinner from "@/components/Spinner";

export default function MemoryPage() {
    const [facts, setFacts] = useState<Fact[]>([]);
    const [loading, setLoading] = useState(false);
    const [loaded, setLoaded] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [query, setQuery] = useState("");

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getFacts();
            setFacts(data);
        } catch (e) {
            setFacts([]);
            setError(e instanceof Error ? e.message : "Could not load memories.");
        } finally {
            setLoaded(true);
            setLoading(false);
        }
    }, []);

    // Load immediately; the page used to wait for a manual Refresh click.
    useEffect(() => {
        load();
    }, [load]);

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return facts;
        return facts.filter(
            (f) =>
                f.fact?.toLowerCase().includes(q) ||
                f.category?.toLowerCase().includes(q)
        );
    }, [facts, query]);

    return (
        <div className="flex flex-col h-full bg-[var(--bg-primary)] text-[var(--text-primary)]">
            <PageHeader
                icon="🧠"
                title="Memory Explorer"
                subtitle="Browse stored facts and memories"
                badge={
                    loaded ? (
                        <span className="badge badge-accent">{facts.length}</span>
                    ) : undefined
                }
                actions={
                    <button
                        onClick={load}
                        disabled={loading}
                        className="btn-secondary text-sm px-4 py-2"
                    >
                        {loading ? <Spinner /> : <RefreshIcon />}
                        <span className="hidden sm:inline">{loading ? "Loading…" : "Refresh"}</span>
                    </button>
                }
            />

            <div className="flex-1 overflow-y-auto p-4 sm:p-6">
                {loaded && facts.length > 0 && (
                    <div className="mb-4 max-w-md">
                        <label className="sr-only" htmlFor="memory-search">
                            Search memories
                        </label>
                        <input
                            id="memory-search"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Search facts or categories…"
                            className="input-modern"
                        />
                    </div>
                )}

                {error && (
                    <div className="mb-4 rounded-lg border border-[var(--error)]/40 bg-[var(--error)]/10 px-3 py-2.5 text-xs text-[var(--text-secondary)]">
                        {error}
                    </div>
                )}

                {!loaded ? (
                    <SkeletonGrid />
                ) : facts.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <div
                            aria-hidden="true"
                            className="w-16 h-16 rounded-2xl bg-[var(--accent-muted)] flex items-center justify-center text-3xl mb-4"
                        >
                            📭
                        </div>
                        <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">
                            No memories yet
                        </h3>
                        <p className="text-[var(--text-muted)] text-sm max-w-xs">
                            Start chatting with Kimiko to build up the memory bank.
                        </p>
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 text-center">
                        <h3 className="text-base font-medium text-[var(--text-primary)] mb-1">
                            No matches
                        </h3>
                        <p className="text-[var(--text-muted)] text-sm">
                            Nothing matched “{query}”.
                        </p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                        {filtered.map((f, i) => (
                            <FactCard key={i} fact={f} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function FactCard({ fact }: { fact: Fact }) {
    const pct = Math.round((fact.confidence || 0) * 100);
    const tone =
        pct >= 70 ? "var(--success)" : pct >= 40 ? "var(--warning)" : "var(--error)";

    return (
        <div className="card p-5 hover:border-[var(--accent)] transition-colors duration-150 animate-fade-up">
            <div className="flex items-center gap-2 mb-3">
                <span className="badge badge-accent">{fact.category || "general"}</span>
                <span className="text-xs font-mono text-[var(--text-muted)] ml-auto">
                    {pct}%
                </span>
            </div>
            <p className="text-sm leading-relaxed text-[var(--text-secondary)] mb-3">
                {fact.fact}
            </p>
            <div
                className="h-1.5 bg-[var(--bg-elevated)] rounded-full overflow-hidden"
                role="meter"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Confidence"
            >
                <div
                    className="h-full rounded-full transition-[width] duration-300"
                    style={{ width: `${pct}%`, backgroundColor: tone }}
                />
            </div>
        </div>
    );
}

function SkeletonGrid() {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="card p-5">
                    <div className="skeleton h-4 w-20 mb-3" />
                    <div className="skeleton h-3 w-full mb-2" />
                    <div className="skeleton h-3 w-4/5 mb-3" />
                    <div className="skeleton h-1.5 w-full" />
                </div>
            ))}
        </div>
    );
}

function RefreshIcon() {
    return (
        <svg
            aria-hidden="true"
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            strokeWidth={2}
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
        </svg>
    );
}
