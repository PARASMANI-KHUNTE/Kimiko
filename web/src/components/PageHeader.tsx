import type { ReactNode } from "react";

interface PageHeaderProps {
    icon: string;
    title: string;
    subtitle?: string;
    badge?: ReactNode;
    actions?: ReactNode;
}

export default function PageHeader({
    icon,
    title,
    subtitle,
    badge,
    actions,
}: PageHeaderProps) {
    return (
        <header className="flex items-center justify-between gap-4 px-4 sm:px-6 py-3 sm:py-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-sm sticky top-0 z-10">
            <div className="flex items-center gap-3 min-w-0">
                <div
                    aria-hidden="true"
                    className="w-9 h-9 rounded-xl bg-[var(--accent-muted)] flex items-center justify-center text-lg shrink-0"
                >
                    {icon}
                </div>
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <h2 className="text-base sm:text-lg font-semibold text-[var(--text-primary)] truncate">
                            {title}
                        </h2>
                        {badge}
                    </div>
                    {subtitle && (
                        <span className="text-xs text-[var(--text-muted)] truncate block">
                            {subtitle}
                        </span>
                    )}
                </div>
            </div>
            {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
    );
}
