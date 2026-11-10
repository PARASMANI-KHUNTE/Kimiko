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
        const interval = setInterval(refresh, 5000);
        return () => clearInterval(interval);
    }, []);

    const toGB = (bytes: number) => (bytes / (1024 ** 3)).toFixed(1);

    return (
        <div className="flex flex-col h-full bg-[var(--bg-primary)] text-[var(--text-primary)]">
            <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-sm sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-[var(--accent-muted)] flex items-center justify-center text-lg">
                        📊
                    </div>
                    <div>
                        <h2 className="text-lg font-semibold text-[var(--text-primary)]">System Metrics</h2>
                        <span className="text-xs text-[var(--text-muted)]">Real-time performance monitoring</span>
                    </div>
                </div>
                <button
                    onClick={refresh}
                    className="btn-secondary text-sm px-4 py-2"
                >
                    <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Refresh
                </button>
            </header>

            <div className="flex-1 overflow-y-auto p-6">
                {/* Status Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                    <MetricCard
                        label="API Status"
                        value={error ? "Offline" : health ? "Online" : "Loading…"}
                        icon={error ? "❌" : health ? "✅" : "⏳"}
                        variant={error ? "error" : health ? "success" : "warning"}
                    />
                    <MetricCard
                        label="Version"
                        value={health?.version || "—"}
                        icon="🏷️"
                    />
                    <MetricCard
                        label="Overall"
                        value={health?.status === "ok" ? "Healthy" : health?.status || "—"}
                        icon={health?.status === "ok" ? "🟢" : "🟡"}
                        variant={health?.status === "ok" ? "success" : "warning"}
                    />
                    <MetricCard
                        label="Last Sync"
                        value={new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        icon="🕐"
                    />
                </div>

                {/* GPU Performance Metrics */}
                <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">
                    GPU & AI Engine
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                    <MetricCard
                        label="VRAM Usage"
                        value={metrics["kimiko_gpu_vram_used_bytes"] ? `${toGB(metrics["kimiko_gpu_vram_used_bytes"])} GB` : "—"}
                        sub={metrics["kimiko_gpu_vram_total_bytes"] ? `of ${toGB(metrics["kimiko_gpu_vram_total_bytes"])} GB` : "nvidia-smi"}
                        icon="💾"
                    />
                    <MetricCard
                        label="GPU Temp"
                        value={metrics["kimiko_gpu_temperature_celsius"] ? `${metrics["kimiko_gpu_temperature_celsius"]}°C` : "—"}
                        sub="Celsius"
                        icon="🌡️"
                    />
                    <MetricCard
                        label="Agent Steps"
                        value={metrics["kimiko_agent_steps_total"]?.toString() || "0"}
                        sub="Total lifetime"
                        icon="👣"
                    />
                    <MetricCard
                        label="Active Runs"
                        value={metrics["kimiko_active_sessions"]?.toString() || "0"}
                        sub="Concurrent"
                        icon="▶️"
                    />
                </div>

                {/* Services */}
                {health?.services && (
                    <>
                        <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">
                            Service Connection Health
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {Object.entries(health.services).map(([name, status]) => (
                                <div
                                    key={name}
                                    className="card p-4 flex items-center gap-4 hover:border-[var(--accent)] transition-colors duration-150"
                                >
                                    <div
                                        className={`w-3 h-3 rounded-full ${status === "ok"
                                                ? "bg-[var(--success)]"
                                                : "bg-[var(--error)]"
                                            }`}
                                    />
                                    <div className="flex-1">
                                        <p className="text-sm font-medium text-[var(--text-primary)] capitalize">{name}</p>
                                        <p className="text-xs text-[var(--text-muted)] font-mono">{status}</p>
                                    </div>
                                    <span className={`badge ${status === "ok" ? "badge-success" : "badge-error"}`}>
                                        {status === "ok" ? "Connected" : "Failed"}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

interface MetricCardProps {
    label: string;
    value: string;
    sub?: string;
    icon?: string;
    variant?: "default" | "success" | "warning" | "error";
}

function MetricCard({ label, value, sub, icon, variant = "default" }: MetricCardProps) {
    const variantStyles = {
        default: "border-[var(--border)]",
        success: "border-[var(--success)]/30 bg-[var(--success)]/5",
        warning: "border-[var(--warning)]/30 bg-[var(--warning)]/5",
        error: "border-[var(--error)]/30 bg-[var(--error)]/5",
    };

    return (
        <div className={`card p-5 ${variantStyles[variant]}`}>
            <div className="flex items-center justify-between mb-2">
                <span className="text-2xl">{icon}</span>
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] mb-1">
                {label}
            </p>
            <p className="text-2xl font-bold text-[var(--text-primary)]">{value}</p>
            {sub && <p className="text-[11px] text-[var(--text-muted)] font-mono mt-1">{sub}</p>}
        </div>
    );
}

