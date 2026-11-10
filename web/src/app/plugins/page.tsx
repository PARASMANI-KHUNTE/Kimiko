"use client";

import { useState } from "react";
import { getPlugins, type Plugin } from "@/lib/api";

export default function PluginsPage() {
    const [plugins, setPlugins] = useState<Plugin[]>([]);
    const [loading, setLoading] = useState(false);
    const [loaded, setLoaded] = useState(false);

    const handleRefresh = async () => {
        setLoading(true);
        try {
            const data = await getPlugins();
            setPlugins(data);
            setLoaded(true);
        } catch {
            setPlugins([]);
        }
        setLoading(false);
    };

    return (
        <div className="flex flex-col h-full bg-[var(--bg-primary)] text-[var(--text-primary)]">
            <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-sm sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-[var(--accent-muted)] flex items-center justify-center text-lg">
                        🔌
                    </div>
                    <div>
                        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Plugin Manager</h2>
                        <span className="text-xs text-[var(--text-muted)]">Manage installed extensions</span>
                    </div>
                </div>
                <button
                    onClick={handleRefresh}
                    disabled={loading}
                    className="btn-secondary text-sm px-4 py-2"
                >
                    {loading ? (
                        <span className="flex items-center gap-2">
                            <span className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                            Loading…
                        </span>
                    ) : (
                        <>
                            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            Refresh
                        </>
                    )}
                </button>
            </header>

            <div className="flex-1 overflow-y-auto p-6">
                {!loaded ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-[var(--text-muted)]">
                            <div className="w-12 h-12 rounded-full border-3 border-[var(--border)] border-t-[var(--accent)] animate-spin mx-auto mb-4" />
                            <p className="text-sm">Loading plugins…</p>
                        </div>
                    </div>
                ) : plugins.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <div className="w-16 h-16 rounded-2xl bg-[var(--accent-muted)] flex items-center justify-center text-3xl mb-4">
                            📦
                        </div>
                        <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">No plugins installed</h3>
                        <p className="text-[var(--text-muted)] text-sm max-w-xs mb-4">Add plugins to extend Kimiko's capabilities.</p>
                        <code className="text-[var(--accent)] bg-[var(--accent-muted)] px-3 py-1.5 rounded-lg text-xs font-mono">
                            src/kimiko/plugins/installed/
                        </code>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {plugins.map((p, i) => (
                            <div
                                key={i}
                                className="card p-4 flex items-center gap-4 hover:border-[var(--accent)] transition-colors duration-150"
                            >
                                <div className="w-12 h-12 rounded-xl bg-[var(--accent-muted)] flex items-center justify-center text-xl shrink-0">
                                    🧩
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate">{p.name}</h3>
                                    <p className="text-xs text-[var(--text-muted)] font-mono mt-0.5">
                                        v{p.version || "?"} by {p.author || "Unknown"}
                                    </p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {(p.capabilities || []).map((cap, j) => (
                                        <span
                                            key={j}
                                            className="badge badge-accent"
                                        >
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

