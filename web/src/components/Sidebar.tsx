"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
    { href: "/", icon: "💬", label: "Chat" },
    { href: "/agent", icon: "🤖", label: "Agent" },
    { href: "/memory", icon: "🧠", label: "Memory" },
    { href: "/plugins", icon: "🔌", label: "Plugins" },
    { href: "/metrics", icon: "📊", label: "Metrics" },
];

export default function Sidebar() {
    const pathname = usePathname();

    return (
        <aside className="w-64 bg-[var(--bg-secondary)] border-r border-[var(--border)] flex flex-col">
            {/* Brand */}
            <div className="flex items-center gap-3 px-5 py-6 border-b border-[var(--border)]">
                <div className="w-10 h-10 rounded-xl bg-[var(--accent)] flex items-center justify-center text-xl">
                    🏯
                </div>
                <h1 className="text-lg font-semibold text-[var(--text-primary)]">Kimiko</h1>
            </div>

            {/* Navigation */}
            <nav className="flex-1 flex flex-col gap-1 p-4 mt-4">
                {navItems.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors duration-150 ${isActive
                                ? "bg-[var(--accent-muted)] text-[var(--accent)]"
                                : "text-[var(--text-secondary)] hover:bg-[var(--bg-card)] hover:text-[var(--text-primary)]"
                                }`}
                        >
                            <span className="text-lg">{item.icon}</span>
                            {item.label}
                        </Link>
                    );
                })}
            </nav>

            {/* Status */}
            <StatusIndicator />
        </aside>
    );
}

function StatusIndicator() {
    return (
        <div className="px-5 py-4 border-t border-[var(--border)] flex items-center gap-3">
            <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-[var(--success)] animate-pulse" />
                <span className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">Online</span>
            </div>
        </div>
    );
}
