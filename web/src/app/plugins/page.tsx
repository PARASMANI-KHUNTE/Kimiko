"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getPlugins, type Plugin } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Spinner from "@/components/Spinner";

export default function PluginsPage() {
    const [plugins, setPlugins] = useState<Plugin[]>([]);
    const [loading, setLoading] = useState(false);
    const [loaded, setLoaded] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [query, setQuery] = useState("");

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getPlugins();
            setPlugins(data);
        } catch (e) {
            setPlugins([]);
            setError(e instanceof Error ? e.message : "Could not load plugins.");
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
        if (!q) return plugins;
        return plugins.filter(
            (p) =>
                p.name?.toLowerCase().includes(q) ||
                p.author?.toLowerCase().includes(q) ||
                p.capabilities?.some((c) => c.toLowerCase().includes(q))
        );
    }, [plugins, query]);

    return (
        <div className="flex flex-col h-full bg-[var(--bg-primary)] text-[var(--text-primary)]">
            <PageHeader
                icon="🔌"
                title="Plugin Manager"
                subtitle="Manage installed extensions"
                badge={
                    loaded ? (
                        <span className="badge badge-accent">{plugins.length}</span>
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
                {loaded && plugins.length > 0 && (
                    <div className="mb-4 max-w-md">
                        <label className="sr-only" htmlFor="plugin-search">
                            Search plugins
                        </label>
                        <input
                            id="plugin-search"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Search plugins or capabilities…"
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
                    <div className="space-y-3">
                        {Array.from({ length: 4 }).map((_, i) => (
                            <div key={i} className="card p-4 flex items-center gap-4">
                                <div className="skeleton w-12 h-12 rounded-xl shrink-0" />
                                <div className="flex-1">
                                    <div className="skeleton h-4 w-40 mb-2" />
                                    <div className="skeleton h-3 w-28" />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : plugins.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <div
                            aria-hidden="true"
                            className="w-16 h-16 rounded-2xl bg-[var(--accent-muted)] flex items-center justify-center text-3xl mb-4"
                        >
                            📦
                        </div>
                        <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">
                            No plugins installed
                        </h3>
                        <p className="text-[var(--text-muted)] text-sm max-w-xs mb-4">
                            Add plugins to extend Kimiko&apos;s capabilities.
                        </p>
                        <code className="text-[var(--accent)] bg-[var(--accent-muted)] px-3 py-1.5 rounded-lg text-xs font-mono">
                            src/kimiko/plugins/installed/
                        </code>
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
                    <div className="space-y-3">
                        {filtered.map((p, i) => (
                            <div
                                key={i}
                                className="card p-4 flex flex-col sm:flex-row sm:items-center gap-4 hover:border-[var(--accent)] transition-colors duration-150 animate-fade-up"
                            >
                                <div
                                    aria-hidden="true"
                                    className="w-12 h-12 rounded-xl bg-[var(--accent-muted)] flex items-center justify-center text-xl shrink-0"
                                >
                                    🧩
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate">
                                        {p.name}
                                    </h3>
                                    <p className="text-xs text-[var(--text-muted)] font-mono mt-0.5">
                                        v{p.version || "?"} by {p.author || "Unknown"}
                                    </p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {(p.capabilities || []).map((cap, j) => (
                                        <span key={j} className="badge badge-accent">
                                            {cap}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
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
