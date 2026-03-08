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
        <div className="flex flex-col h-full">
            <div className="flex items-center justify-between px-7 py-5 border-b border-gray-800">
                <h2 className="text-lg font-semibold">🔌 Active Plugins</h2>
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
                            <p className="text-4xl mb-4">🔌</p>
                            <p className="text-lg font-medium">Plugin Manager</p>
                            <p className="text-sm mt-2">Click Refresh to load installed plugins.</p>
                        </div>
                    </div>
                ) : plugins.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-gray-500">
                            <p className="text-4xl mb-4">📦</p>
                            <p>No plugins installed yet.</p>
                            <p className="text-sm mt-2">Add plugins to <code className="text-violet-400">src/kimiko/plugins/installed/</code></p>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {plugins.map((p, i) => (
                            <div
                                key={i}
                                className="flex items-center gap-4 bg-[#1a1a2e] border border-gray-800 rounded-xl px-5 py-4 hover:bg-[#222240] transition-all animate-fade-in"
                            >
                                <div className="text-2xl">🧩</div>
                                <div className="flex-1">
                                    <h3 className="text-sm font-semibold text-gray-100">{p.name}</h3>
                                    <p className="text-xs text-gray-500 mt-0.5">
                                        v{p.version || "?"} by {p.author || "Unknown"}
                                    </p>
                                </div>
                                <div className="flex gap-2">
                                    {(p.capabilities || []).map((cap, j) => (
                                        <span
                                            key={j}
                                            className="text-[11px] px-3 py-1 rounded-full bg-violet-500/15 text-violet-400 font-medium"
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
