"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { checkHealth, getMetrics } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Spinner from "@/components/Spinner";

interface HealthData {
    status: string;
    version: string;
    services: Record<string, string>;
}

export default function MetricsPage() {
    const [health, setHealth] = useState<HealthData | null>(null);
    const [metrics, setMetrics] = useState<Record<string, number>>({});
    const [error, setError] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const refresh = useCallback(async () => {
        setRefreshing(true);
        try {
            const [hData, mData] = await Promise.all([checkHealth(), getMetrics()]);
            setHealth(hData);
            setMetrics(mData);
            setError(false);
            setLastUpdated(new Date());
        } catch {
            setError(true);
        } finally {
            setRefreshing(false);
        }
    }, []);

    useEffect(() => {
        refresh();
        const interval = setInterval(() => {
            // Don't hammer the backend while the tab is hidden.
            if (typeof document === "undefined" || !document.hidden) refresh();
        }, 5000);

        const onVisible = () => {
            if (!document.hidden) refresh();
        };
        document.addEventListener("visibilitychange", onVisible);

        return () => {
            clearInterval(interval);
            document.removeEventListener("visibilitychange", onVisible);
        };
    }, [refresh]);

    const toGB = (bytes?: number) =>
        typeof bytes === "number" && bytes > 0 ? (bytes / 1024 ** 3).toFixed(1) : "—";

    const num = (value?: number) =>
        typeof value === "number" ? value.toLocaleString() : "—";

    const vramUsed = metrics["kimiko_gpu_vram_used_bytes"];
    const vramTotal = metrics["kimiko_gpu_vram_total_bytes"];
    const vramPct =
        vramUsed && vramTotal && vramTotal > 0
            ? Math.min(100, Math.round((vramUsed / vramTotal) * 100))
            : null;

    return (
        <div className="flex flex-col h-full bg-[var(--bg-primary)] text-[var(--text-primary)]">
            <PageHeader
                icon="📊"
                title="System Metrics"
                subtitle={
                    lastUpdated
                        ? `Updated ${lastUpdated.toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                              second: "2-digit",
                          })}`
                        : "Real-time performance monitoring"
                }
                actions={
                    <button
                        onClick={refresh}
                        disabled={refreshing}
                        className="btn-secondary text-sm px-4 py-2"
                    >
                        {refreshing ? <Spinner /> : <RefreshIcon />}
                        <span className="hidden sm:inline">
                            {refreshing ? "Refreshing…" : "Refresh"}
                        </span>
                    </button>
                }
            />

            <div className="flex-1 overflow-y-auto p-4 sm:p-6">
                {error && (
                    <div className="mb-6 flex items-center gap-3 rounded-lg border border-[var(--error)]/40 bg-[var(--error)]/10 px-3 py-2.5 text-xs text-[var(--text-secondary)]">
                        <span aria-hidden="true">⚠️</span>
                        <span className="flex-1">
                            Could not reach the Kimiko API. Showing the last known values.
                        </span>
                        <button
                            onClick={refresh}
                            className="font-semibold text-[var(--accent)] hover:underline"
                        >
                            Retry
                        </button>
                    </div>
                )}

                {/* Status Cards */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                    <MetricCard
                        label="API Status"
                        value={error ? "Offline" : health ? "Online" : "Loading…"}
                        icon={error ? "❌" : health ? "✅" : "⏳"}
                        variant={error ? "error" : health ? "success" : "warning"}
                    />
                    <MetricCard label="Version" value={health?.version || "—"} icon="🏷️" />
                    <MetricCard
                        label="Overall"
                        value={health?.status === "ok" ? "Healthy" : health?.status || "—"}
                        icon={health?.status === "ok" ? "🟢" : "🟡"}
                        variant={health?.status === "ok" ? "success" : "warning"}
                    />
                    <MetricCard
                        label="Last Sync"
                        value={
                            lastUpdated
                                ? lastUpdated.toLocaleTimeString([], {
                                      hour: "2-digit",
                                      minute: "2-digit",
                                      second: "2-digit",
                                  })
                                : "—"
                        }
                        icon="🕐"
                    />
                </div>

                {/* GPU Performance Metrics */}
                <SectionTitle>GPU &amp; AI Engine</SectionTitle>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                    <MetricCard
                        label="VRAM Usage"
                        value={vramUsed ? `${toGB(vramUsed)} GB` : "—"}
                        sub={vramTotal ? `of ${toGB(vramTotal)} GB` : "nvidia-smi"}
                        icon="💾"
                        progress={vramPct}
                    />
                    <MetricCard
                        label="GPU Utilization"
                        value={
                            metrics["kimiko_gpu_utilization_percent"] !== undefined
                                ? `${Math.round(metrics["kimiko_gpu_utilization_percent"])}%`
                                : "—"
                        }
                        sub="Compute load"
                        icon="⚙️"
                        progress={
                            metrics["kimiko_gpu_utilization_percent"] !== undefined
                                ? Math.min(100, Math.round(metrics["kimiko_gpu_utilization_percent"]))
                                : null
                        }
                    />
                    <MetricCard
                        label="GPU Temp"
                        value={
                            metrics["kimiko_gpu_temperature_celsius"] !== undefined
                                ? `${Math.round(metrics["kimiko_gpu_temperature_celsius"])}°C`
                                : "—"
                        }
                        sub="Celsius"
                        icon="🌡️"
                    />
                    <MetricCard
                        label="Active Sessions"
                        value={num(metrics["kimiko_active_sessions"])}
                        sub={`${num(metrics["kimiko_stream_connections_active"])} streaming`}
                        icon="▶️"
                    />
                </div>

                {/* Activity */}
                <SectionTitle>Activity</SectionTitle>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                    <MetricCard
                        label="HTTP Requests"
                        value={num(metrics["kimiko_http_requests_total"])}
                        sub="Total lifetime"
                        icon="🌐"
                    />
                    <MetricCard
                        label="Tokens Generated"
                        value={num(metrics["kimiko_llm_tokens_generated_total"])}
                        sub="All models"
                        icon="🔤"
                    />
                    <MetricCard
                        label="Agent Steps"
                        value={num(metrics["kimiko_agent_steps_total"])}
                        sub={`${num(metrics["kimiko_agent_failures_total"])} failures`}
                        icon="👣"
                    />
                    <MetricCard
                        label="LLM Errors"
                        value={num(metrics["kimiko_llm_errors_total"])}
                        sub="Total lifetime"
                        icon="🚨"
                        variant={
                            (metrics["kimiko_llm_errors_total"] ?? 0) > 0 ? "error" : "default"
                        }
                    />
                </div>

                {/* Services */}
                {health?.services && (
                    <>
                        <SectionTitle>Service Connection Health</SectionTitle>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                            {Object.entries(health.services).map(([name, status]) => {
                                const ok = status === "ok";
                                return (
                                    <div
                                        key={name}
                                        className="card p-4 flex items-center gap-4 hover:border-[var(--accent)] transition-colors duration-150"
                                    >
                                        <div
                                            aria-hidden="true"
                                            className={`w-3 h-3 rounded-full ${ok ? "bg-[var(--success)]" : "bg-[var(--error)]"
                                                }`}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-[var(--text-primary)] capitalize truncate">
                                                {name}
                                            </p>
                                            <p className="text-xs text-[var(--text-muted)] font-mono truncate">
                                                {status}
                                            </p>
                                        </div>
                                        <span
                                            className={`badge ${ok ? "badge-success" : "badge-error"}`}
                                        >
                                            {ok ? "Connected" : "Failed"}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

function SectionTitle({ children }: { children: ReactNode }) {
    return (
        <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">
            {children}
        </h3>
    );
}

interface MetricCardProps {
    label: string;
    value: string;
    sub?: string;
    icon?: string;
    variant?: "default" | "success" | "warning" | "error";
    progress?: number | null;
}

function MetricCard({
    label,
    value,
    sub,
    icon,
    variant = "default",
    progress,
}: MetricCardProps) {
    const variantStyles = {
        default: "border-[var(--border)]",
        success: "border-[var(--success)]/30 bg-[var(--success)]/5",
        warning: "border-[var(--warning)]/30 bg-[var(--warning)]/5",
        error: "border-[var(--error)]/30 bg-[var(--error)]/5",
    };

    return (
        <div className={`card p-4 sm:p-5 ${variantStyles[variant]}`}>
            <div className="flex items-center justify-between mb-2">
                <span aria-hidden="true" className="text-2xl">
                    {icon}
                </span>
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] mb-1">
                {label}
            </p>
            <p className="text-xl sm:text-2xl font-bold text-[var(--text-primary)] truncate">
                {value}
            </p>
            {typeof progress === "number" && (
                <div className="mt-2 h-1.5 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                    <div
                        className="h-full bg-[var(--accent)] rounded-full transition-[width] duration-300"
                        style={{ width: `${progress}%` }}
                    />
                </div>
            )}
            {sub && <p className="text-[11px] text-[var(--text-muted)] font-mono mt-1">{sub}</p>}
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
