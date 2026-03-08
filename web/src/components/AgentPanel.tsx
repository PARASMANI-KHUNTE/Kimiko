"use client";

import { useState } from "react";
import { runAgent } from "@/lib/api";

interface TraceStep {
    text: string;
}

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
        <div className="flex flex-col h-full bg-[#0a0a0f]">
            <div className="px-7 py-5 border-b border-gray-800">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                    🤖 Agent Task Runner
                    <span className="text-[10px] bg-amber-500/20 text-amber-500 px-2 py-0.5 rounded-full uppercase tracking-tighter">Beta</span>
                </h2>
                <p className="text-xs text-gray-500 mt-1">Run complex tasks involving tools and multi-step reasoning.</p>
            </div>

            <div className="flex-1 overflow-y-auto p-7 space-y-6">
                {/* Input */}
                <div className="space-y-3">
                    <label className="text-xs font-semibold uppercase tracking-wider text-gray-500">Goal / Objective</label>
                    <div className="flex gap-3">
                        <input
                            value={goal}
                            onChange={(e) => setGoal(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleRun()}
                            placeholder="e.g. Find news about Kimiko and summarize it..."
                            className="flex-1 bg-[#16162a] border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-100 outline-none focus:border-violet-500 transition-all"
                        />
                        <button
                            onClick={handleRun}
                            disabled={loading}
                            className="bg-amber-500 hover:bg-amber-600 text-black font-bold px-6 py-3 rounded-xl text-sm transition-all disabled:opacity-50"
                        >
                            {loading ? "Running..." : "Run Agent"}
                        </button>
                    </div>
                </div>

                {/* Results */}
                {loading && (
                    <div className="space-y-4 animate-pulse">
                        <div className="h-4 bg-gray-800 rounded w-1/4"></div>
                        <div className="space-y-2">
                            <div className="h-10 bg-gray-900 rounded-xl"></div>
                            <div className="h-10 bg-gray-900 rounded-xl"></div>
                        </div>
                    </div>
                )}

                {result && (
                    <div className="space-y-6 animate-fade-in">
                        {/* Steps Trace */}
                        <div className="space-y-3">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Reasoning Trace</h3>
                            <div className="space-y-2">
                                {result.steps.map((step, i) => (
                                    <div key={i} className="flex gap-3 bg-[#111118] border border-gray-800 rounded-xl p-4 text-xs leading-relaxed text-gray-300">
                                        <span className="text-amber-500 font-mono font-bold">STEP {i + 1}</span>
                                        <p>{step}</p>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Final Answer */}
                        <div className="space-y-3">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Final Conclusion</h3>
                            <div className="bg-gradient-to-br from-[#1a1a2e] to-[#12121a] border border-violet-500/30 rounded-xl p-6 text-sm leading-relaxed text-gray-100 shadow-xl shadow-violet-500/5">
                                {result.answer}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
