interface SpinnerProps {
    size?: "sm" | "md" | "lg";
    className?: string;
}

const sizes = {
    sm: "w-3.5 h-3.5 border-2",
    md: "w-5 h-5 border-2",
    lg: "w-10 h-10 border-[3px]",
};

export default function Spinner({ size = "sm", className = "" }: SpinnerProps) {
    return (
        <span
            role="status"
            aria-label="Loading"
            className={`inline-block rounded-full border-[var(--border-strong)] border-t-[var(--accent)] animate-spin ${sizes[size]} ${className}`}
        />
    );
}
