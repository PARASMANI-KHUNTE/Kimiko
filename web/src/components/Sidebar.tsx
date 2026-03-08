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
        <aside className="w-60 bg-[#111118] border-r border-gray-800 flex flex-col">
            {/* Brand */}
            <div className="flex items-center gap-3 px-5 py-5 border-b border-gray-800">
                <span className="text-3xl">🏯</span>
                <h1 className="text-xl font-bold gradient-text">Kimiko</h1>
            </div>

            {/* Navigation */}
            <nav className="flex-1 flex flex-col gap-1 p-3 mt-2">
                {navItems.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${isActive
                                ? "bg-gradient-to-r from-violet-500/20 to-emerald-500/10 text-violet-400 border-l-3 border-violet-500"
                                : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
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
        <div className="px-5 py-4 border-t border-gray-800 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_theme(colors.emerald.400)]" />
            <span className="text-xs text-gray-500">Online</span>
        </div>
    );
}
