"use client";

import { useState } from "react";
import { runAgent } from "@/lib/api";

export default function AgentPanel() {
    const [goal, setGoal] = useState("");
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ answer: string; steps: string[] } | null>(null);

    const handleRun = async () => {
        if (!goal.trim() || loading) return;
        setLoading(true);
        setResult(null);
        try {
            const data = await runAgent(goal);
            setResult(data);
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    return (
        <div className="flex flex-col h-full bg-[var(--bg-primary)] text-[var(--text-primary)]">
            <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-sm sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-[var(--accent-muted)] flex items-center justify-center text-lg">
                        🤖
                    </div>
                    <div>
                        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Agent Task Runner</h2>
                        <span className="text-xs text-[var(--text-muted)]">Multi-step reasoning with tools</span>
                    </div>
                </div>
                <span className="badge badge-accent">Beta</span>
            </header>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* Input */}
                <div className="space-y-3">
                    <label className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Goal / Objective</label>
                    <div className="flex gap-3">
                        <input
                            value={goal}
                            onChange={(e) => setGoal(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleRun()}
                            placeholder="e.g. Find news about Kimiko and summarize it..."
                            className="flex-1 input-modern bg-[var(--bg-card)]"
                        />
                        <button
                            onClick={handleRun}
                            disabled={loading || !goal.trim()}
                            className="btn-primary px-6 py-3 whitespace-nowrap"
                        >
                            {loading ? (
                                <span className="flex items-center gap-2">
                                    <span className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                                    Running…
                                </span>
                            ) : (
                                "Run Agent"
                            )}
                        </button>
                    </div>
                </div>

                {/* Results */}
                {loading && (
                    <div className="space-y-4 animate-in fade-in duration-200">
                        <div className="h-4 bg-[var(--bg-elevated)] rounded w-1/4 animate-pulse" />
                        <div className="space-y-3">
                            <div className="h-12 bg-[var(--bg-elevated)] rounded-xl animate-pulse" />
                            <div className="h-12 bg-[var(--bg-elevated)] rounded-xl animate-pulse" />
                        </div>
                    </div>
                )}

                {result && (
                    <div className="space-y-6 animate-in fade-in slide-y-2 duration-200">
                        {/* Steps Trace */}
                        <div className="space-y-3">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Reasoning Trace</h3>
                            <div className="space-y-2">
                                {result.steps.map((step, i) => (
                                    <div key={i} className="card p-4 flex gap-4">
                                        <span className="text-[var(--accent)] font-mono font-bold text-xs shrink-0">STEP {i + 1}</span>
                                        <p className="text-sm text-[var(--text-secondary)] leading-relaxed flex-1">{step}</p>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Final Answer */}
                        <div className="space-y-3">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Final Conclusion</h3>
                            <div className="card-elevated p-6 border-[var(--accent)]">
                                <p className="text-sm text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">{result.answer}</p>
                            </div>
                        </div>
                    </div>
                )}

                {!loading && !result && (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                        <div className="w-16 h-16 rounded-2xl bg-[var(--accent-muted)] flex items-center justify-center text-3xl mb-4">
                            🤖
                        </div>
                        <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">Ready to run tasks</h3>
                        <p className="text-[var(--text-muted)] text-sm max-w-md">Enter a goal above and click Run Agent to start multi-step reasoning.</p>
                    </div>
                )}
            </div>
        </div>
    );
}

