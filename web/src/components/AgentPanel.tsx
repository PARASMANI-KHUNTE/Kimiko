"use client";

import { useCallback, useRef, useState } from "react";
import { runAgent } from "@/lib/api";
import PageHeader from "@/components/PageHeader";

const EXAMPLES = [
    "Search the web for the latest AI news and summarize it",
    "Plan a 3-step workflow to organize my project files",
    "Check the weather and suggest what to wear",
];

export default function AgentPanel() {
    const [goal, setGoal] = useState("");
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ answer: string; steps: string[] } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const abortRef = useRef<AbortController | null>(null);

    const run = useCallback(async (raw: string) => {
        const prompt = raw.trim();
        if (!prompt || loading) return;

        setLoading(true);
        setError(null);
        setResult(null);

        const controller = new AbortController();
        abortRef.current = controller;

        try {
            const data = await runAgent(prompt, 5, controller.signal);
            setResult({
                answer: data.answer,
                steps: Array.isArray(data.steps) ? data.steps : [],
            });
        } catch (e) {
            if (!controller.signal.aborted) {
                setError(e instanceof Error ? e.message : "The agent could not complete this task.");
            }
        } finally {
            setLoading(false);
            abortRef.current = null;
        }
    }, [loading]);

    const handleStop = () => abortRef.current?.abort();

    return (
        <div className="flex flex-col h-full bg-[var(--bg-primary)] text-[var(--text-primary)]">
            <PageHeader
                icon="🤖"
                title="Agent Task Runner"
                subtitle="Multi-step reasoning with tools"
                badge={<span className="badge badge-accent">Beta</span>}
            />

            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
                {/* Input */}
                <div className="space-y-3">
                    <label
                        htmlFor="agent-goal"
                        className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]"
                    >
                        Goal / Objective
                    </label>
                    <div className="flex flex-col sm:flex-row gap-3">
                        <input
                            id="agent-goal"
                            value={goal}
                            onChange={(e) => setGoal(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                                    e.preventDefault();
                                    run(goal);
                                }
                            }}
                            placeholder="e.g. Find news about Kimiko and summarize it…"
                            className="flex-1 input-modern bg-[var(--bg-card)]"
                        />
                        {loading ? (
                            <button
                                type="button"
                                onClick={handleStop}
                                className="btn-danger px-6 py-3 whitespace-nowrap"
                            >
                                <span aria-hidden="true">■</span> Stop
                            </button>
                        ) : (
                            <button
                                type="button"
                                onClick={() => run(goal)}
                                disabled={!goal.trim()}
                                className="btn-primary px-6 py-3 whitespace-nowrap"
                            >
                                Run Agent
                            </button>
                        )}
                    </div>

                    {!result && !loading && (
                        <div className="flex flex-wrap gap-2 pt-1">
                            {EXAMPLES.map((ex) => (
                                <button
                                    key={ex}
                                    type="button"
                                    onClick={() => setGoal(ex)}
                                    className="btn-ghost text-xs border border-[var(--border)] rounded-full px-3 py-1.5"
                                >
                                    {ex}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {error && (
                    <div className="flex items-start gap-3 rounded-lg border border-[var(--error)]/40 bg-[var(--error)]/10 px-3 py-2.5 animate-fade-in">
                        <span aria-hidden="true" className="text-sm">
                            ⚠️
                        </span>
                        <p className="flex-1 text-xs text-[var(--text-secondary)]">{error}</p>
                        <button
                            type="button"
                            onClick={() => run(goal)}
                            disabled={loading || !goal.trim()}
                            className="text-xs font-semibold text-[var(--accent)] hover:underline disabled:opacity-50"
                        >
                            Retry
                        </button>
                    </div>
                )}

                {/* Results */}
                {loading && (
                    <div className="space-y-4 animate-fade-in" aria-label="Running agent">
                        <div className="skeleton h-4 w-1/4" />
                        <div className="space-y-3">
                            <div className="skeleton h-16 rounded-xl" />
                            <div className="skeleton h-16 rounded-xl" />
                            <div className="skeleton h-24 rounded-xl" />
                        </div>
                    </div>
                )}

                {result && (
                    <div className="space-y-6 animate-fade-up">
                        {/* Steps Trace */}
                        {result.steps.length > 0 && (
                            <div className="space-y-3">
                                <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                                    Reasoning Trace ({result.steps.length}{" "}
                                    {result.steps.length === 1 ? "step" : "steps"})
                                </h3>
                                <div className="space-y-2">
                                    {result.steps.map((step, i) => (
                                        <div
                                            key={i}
                                            className="card p-4 flex gap-4 animate-fade-up"
                                            style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
                                        >
                                            <span className="text-[var(--accent)] font-mono font-bold text-xs shrink-0">
                                                STEP {i + 1}
                                            </span>
                                            <p className="text-sm text-[var(--text-secondary)] leading-relaxed flex-1 whitespace-pre-wrap break-words">
                                                {step}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Final Answer */}
                        <div className="space-y-3">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                                Final Conclusion
                            </h3>
                            <div className="card-elevated p-5 sm:p-6 border-[var(--accent)]">
                                <p className="text-sm text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap break-words">
                                    {result.answer}
                                </p>
                            </div>
                        </div>

                        <button
                            type="button"
                            onClick={() => {
                                setResult(null);
                                setGoal("");
                            }}
                            className="btn-secondary text-sm px-4 py-2"
                        >
                            Run another task
                        </button>
                    </div>
                )}

                {!loading && !result && !error && (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                        <div
                            aria-hidden="true"
                            className="w-16 h-16 rounded-2xl bg-[var(--accent-muted)] flex items-center justify-center text-3xl mb-4"
                        >
                            🤖
                        </div>
                        <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">
                            Ready to run tasks
                        </h3>
                        <p className="text-[var(--text-muted)] text-sm max-w-md">
                            Enter a goal above and click Run Agent to start multi-step reasoning.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
