"use client";

import { useState, useEffect } from "react";
import { checkHealth } from "@/lib/api";

interface HealthData {
    status: string;
    version: string;
    services: Record<string, string>;
}

export default function MetricsPage() {
    const [health, setHealth] = useState<HealthData | null>(null);
    const [metrics, setMetrics] = useState<Record<string, number>>({});
    const [error, setError] = useState(false);

    const refresh = async () => {
        try {
            const { checkHealth, getMetrics } = await import("@/lib/api");
            const [hData, mData] = await Promise.all([checkHealth(), getMetrics()]);
            setHealth(hData);
            setMetrics(mData);
            setError(false);
        } catch {
            setError(true);
        }
    };

    useEffect(() => {
        refresh();
        const interval = setInterval(refresh, 5000); // Faster refresh for metrics
        return () => clearInterval(interval);
    }, []);

    // Helper to format bytes to GB
    const toGB = (bytes: number) => (bytes / (1024 ** 3)).toFixed(1);

    return (
        <div className="flex flex-col h-full">
            <div className="flex items-center justify-between px-7 py-5 border-b border-gray-800">
                <h2 className="text-lg font-semibold">📊 System Metrics</h2>
                <button
                    onClick={refresh}
                    className="bg-[#1a1a2e] border border-gray-700 text-gray-400 px-4 py-2 rounded-lg text-sm hover:bg-gray-800 hover:text-gray-200 transition-all font-medium"
                >
                    ↻ Refresh
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-7">
                {/* Status Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                    <MetricCard
                        label="API Status"
                        value={error ? "❌ Offline" : health ? "✅ Online" : "..."}
                    />
                    <MetricCard
                        label="Version"
                        value={health?.version || "—"}
                    />
                    <MetricCard
                        label="Overall"
                        value={health?.status === "ok" ? "🟢 Healthy" : health?.status || "—"}
                    />
                    <MetricCard
                        label="Last Sync"
                        value={new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    />
                </div>

                {/* GPU Performance Metrics */}
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                    GPU & AI Engine
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                    <MetricCard
                        label="VRAM Usage"
                        value={metrics["kimiko_gpu_vram_used_bytes"] ? `${toGB(metrics["kimiko_gpu_vram_used_bytes"])} GB` : "—"}
                        sub={metrics["kimiko_gpu_vram_total_bytes"] ? `of ${toGB(metrics["kimiko_gpu_vram_total_bytes"])} GB` : "nvidia-smi"}
                    />
                    <MetricCard
                        label="GPU Temp"
                        value={metrics["kimiko_gpu_temperature_celsius"] ? `${metrics["kimiko_gpu_temperature_celsius"]}°C` : "—"}
                        sub="Celsius"
                    />
                    <MetricCard
                        label="Agent Steps"
                        value={metrics["kimiko_agent_steps_total"]?.toString() || "0"}
                        sub="Total lifetime"
                    />
                    <MetricCard
                        label="Active Runs"
                        value={metrics["kimiko_active_sessions"]?.toString() || "0"}
                        sub="Concurrent"
                    />
                </div>

                {/* Services */}
                {health?.services && (
                    <>
                        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                            Service Connection Health
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {Object.entries(health.services).map(([name, status]) => (
                                <div
                                    key={name}
                                    className="bg-[#1a1a2e] border border-gray-800 rounded-xl p-5 flex items-center gap-4 hover:border-gray-700 transition-colors"
                                >
                                    <div
                                        className={`w-3 h-3 rounded-full ${status === "ok"
                                                ? "bg-emerald-400 shadow-[0_0_8px_theme(colors.emerald.400)]"
                                                : "bg-red-400 shadow-[0_0_8px_theme(colors.red.400)]"
                                            }`}
                                    />
                                    <div>
                                        <p className="text-sm font-medium capitalize">{name}</p>
                                        <p className="text-xs text-gray-500">{status}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
    return (
        <div className="bg-[#1a1a2e] border border-gray-800 rounded-xl p-5 text-center">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 mb-2">
                {label}
            </p>
            <p className="text-2xl font-bold gradient-text">{value}</p>
            {sub && <p className="text-[11px] text-gray-600 mt-1">{sub}</p>}
        </div>
    );
}
