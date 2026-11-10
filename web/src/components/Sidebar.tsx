"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { checkHealth } from "@/lib/api";

type NavItem = {
    href: string;
    icon: string;
    label: string;
};

const navItems: NavItem[] = [
    { href: "/", icon: "💬", label: "Chat" },
    { href: "/agent", icon: "🤖", label: "Agent" },
    { href: "/memory", icon: "🧠", label: "Memory" },
    { href: "/plugins", icon: "🔌", label: "Plugins" },
    { href: "/metrics", icon: "📊", label: "Metrics" },
];

export default function Sidebar() {
    const pathname = usePathname();

    return (
        <>
            {/* Desktop / tablet sidebar */}
            <aside className="hidden md:flex w-64 shrink-0 bg-[var(--bg-secondary)] border-r border-[var(--border)] flex-col">
                {/* Brand */}
                <div className="flex items-center gap-3 px-5 py-6 border-b border-[var(--border)]">
                    <div
                        aria-hidden="true"
                        className="w-10 h-10 rounded-xl bg-[var(--accent)] flex items-center justify-center text-xl shadow-sm"
                    >
                        🏯
                    </div>
                    <div className="min-w-0">
                        <h1 className="text-lg font-semibold text-[var(--text-primary)] leading-tight">
                            Kimiko
                        </h1>
                        <p className="text-[11px] text-[var(--text-muted)]">Local AI assistant</p>
                    </div>
                </div>

                {/* Navigation */}
                <nav aria-label="Primary" className="flex-1 flex flex-col gap-1 p-4 mt-2">
                    {navItems.map((item) => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                aria-current={isActive ? "page" : undefined}
                                className={`group relative flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors duration-150 ${isActive
                                    ? "bg-[var(--accent-muted)] text-[var(--accent)]"
                                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-card)] hover:text-[var(--text-primary)]"
                                    }`}
                            >
                                <span
                                    aria-hidden="true"
                                    className="text-lg transition-transform duration-150 group-hover:scale-110"
                                >
                                    {item.icon}
                                </span>
                                {item.label}
                                {isActive && (
                                    <span
                                        aria-hidden="true"
                                        className="absolute left-0 top-1/2 -translate-y-1/2 h-6 w-1 rounded-r-full bg-[var(--accent)]"
                                    />
                                )}
                            </Link>
                        );
                    })}
                </nav>

                <ServiceStatus />
            </aside>

            {/* Mobile bottom navigation */}
            <nav
                aria-label="Primary"
                className="md:hidden fixed bottom-0 inset-x-0 z-30 h-16 bg-[var(--bg-secondary)]/95 backdrop-blur border-t border-[var(--border)] flex items-stretch"
            >
                {navItems.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            aria-current={isActive ? "page" : undefined}
                            className={`flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors ${isActive
                                ? "text-[var(--accent)]"
                                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                                }`}
                        >
                            <span aria-hidden="true" className="text-lg leading-none">
                                {item.icon}
                            </span>
                            {item.label}
                        </Link>
                    );
                })}
            </nav>
        </>
    );
}

function ServiceStatus() {
    const [status, setStatus] = useState<"checking" | "online" | "offline">("checking");

    useEffect(() => {
        let cancelled = false;

        const probe = async () => {
            if (typeof document !== "undefined" && document.hidden) return;
            try {
                const health = await checkHealth();
                if (!cancelled) {
                    setStatus(health.status === "ok" ? "online" : "offline");
                }
            } catch {
                if (!cancelled) setStatus("offline");
            }
        };

        probe();
        const interval = setInterval(probe, 20_000);
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, []);

    const meta = {
        checking: { dot: "bg-[var(--warning)]", text: "Checking…", label: "Checking API status" },
        online: { dot: "bg-[var(--success)]", text: "Online", label: "API is online" },
        offline: { dot: "bg-[var(--error)]", text: "Offline", label: "API is offline" },
    }[status];

    return (
        <div
            className="px-5 py-4 border-t border-[var(--border)] flex items-center gap-3"
            title={meta.label}
        >
            <span
                aria-hidden="true"
                className={`w-2 h-2 rounded-full ${meta.dot} ${status === "online" ? "animate-pulse" : ""}`}
            />
            <div className="min-w-0">
                <p className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">
                    {meta.text}
                </p>
                <p className="text-[11px] text-[var(--text-muted)] truncate">Kimiko API</p>
            </div>
            <span className="sr-only" role="status">
                {meta.label}
            </span>
        </div>
    );
}
