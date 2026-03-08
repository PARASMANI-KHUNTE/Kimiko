"use client";

import { useState } from "react";
import { getFacts, type Fact } from "@/lib/api";

export default function MemoryPage() {
    const [facts, setFacts] = useState<Fact[]>([]);
    const [loading, setLoading] = useState(false);
    const [loaded, setLoaded] = useState(false);

    const handleRefresh = async () => {
        setLoading(true);
        try {
            const data = await getFacts();
            setFacts(data);
            setLoaded(true);
        } catch {
            setFacts([]);
        }
        setLoading(false);
    };

    return (
        <div className="flex flex-col h-full">
            <div className="flex items-center justify-between px-7 py-5 border-b border-gray-800">
                <h2 className="text-lg font-semibold">🧠 Memory Explorer</h2>
                <button
                    onClick={handleRefresh}
                    disabled={loading}
                    className="bg-[#1a1a2e] border border-gray-700 text-gray-400 px-4 py-2 rounded-lg text-sm hover:bg-gray-800 hover:text-gray-200 transition-all disabled:opacity-50"
                >
                    {loading ? "Loading..." : "↻ Refresh"}
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-7">
                {!loaded ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-gray-500">
                            <p className="text-4xl mb-4">🧠</p>
                            <p className="text-lg font-medium">Memory Explorer</p>
                            <p className="text-sm mt-2">Click Refresh to load Kimiko&apos;s stored facts and memories.</p>
                        </div>
                    </div>
                ) : facts.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-gray-500">
                            <p className="text-4xl mb-4">📭</p>
                            <p>No facts stored yet. Start chatting with Kimiko!</p>
                        </div>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {facts.map((f, i) => (
                            <div
                                key={i}
                                className="bg-[#1a1a2e] border border-gray-800 rounded-xl p-5 hover:-translate-y-0.5 hover:shadow-[0_4px_24px_rgba(0,0,0,0.4)] transition-all animate-fade-in"
                            >
                                <div className="text-[11px] font-semibold uppercase tracking-wider text-violet-400 mb-2">
                                    {f.category || "general"}
                                </div>
                                <p className="text-sm text-gray-200 leading-relaxed mb-3">
                                    {f.fact}
                                </p>
                                <div className="text-xs text-gray-500 mb-1">
                                    Confidence: {Math.round((f.confidence || 0) * 100)}%
                                </div>
                                <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-gradient-to-r from-violet-500 to-emerald-400 rounded-full transition-all duration-500"
                                        style={{ width: `${Math.round((f.confidence || 0) * 100)}%` }}
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
