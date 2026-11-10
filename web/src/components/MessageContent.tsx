"use client";

import { useState } from "react";

interface MessageContentProps {
    content: string;
}

type Segment =
    | { type: "text"; content: string }
    | { type: "code"; content: string; lang?: string };

/**
 * Split chat text into plain-text and fenced-code segments.
 *
 * Written as a small state machine (rather than one regex) so it degrades
 * gracefully while a response is still streaming: an unterminated ``` fence is
 * rendered as code until the closing fence arrives.
 */
function parseSegments(content: string): Segment[] {
    const segments: Segment[] = [];
    let index = 0;

    while (index < content.length) {
        const start = content.indexOf("```", index);
        if (start === -1) {
            segments.push({ type: "text", content: content.slice(index) });
            break;
        }

        if (start > index) {
            segments.push({ type: "text", content: content.slice(index, start) });
        }

        const afterFence = start + 3;
        const newline = content.indexOf("\n", afterFence);
        let lang: string | undefined;
        let bodyStart = afterFence;

        if (newline !== -1) {
            const candidate = content.slice(afterFence, newline).trim();
            if (candidate && !candidate.includes(" ")) {
                lang = candidate;
                bodyStart = newline + 1;
            }
        }

        const end = content.indexOf("```", bodyStart);
        if (end === -1) {
            // Still streaming: treat the remainder as an open code block.
            segments.push({
                type: "code",
                lang,
                content: content.slice(bodyStart),
            });
            break;
        }

        segments.push({
            type: "code",
            lang,
            content: content.slice(bodyStart, end).replace(/\n$/, ""),
        });
        index = end + 3;
    }

    return segments;
}

function renderInline(text: string) {
    // Style `inline code` without pulling in a full markdown parser.
    return text.split(/(`[^`\n]+`)/g).map((part, i) =>
        part.length > 2 && part.startsWith("`") && part.endsWith("`") ? (
            <code
                key={i}
                className="px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] border border-[var(--border)] font-mono text-[0.85em] text-[var(--accent)]"
            >
                {part.slice(1, -1)}
            </code>
        ) : (
            <span key={i}>{part}</span>
        )
    );
}

export default function MessageContent({ content }: MessageContentProps) {
    const segments = parseSegments(content);

    return (
        <div className="space-y-3">
            {segments.map((segment, i) =>
                segment.type === "code" ? (
                    <CodeBlock key={i} code={segment.content} lang={segment.lang} />
                ) : (
                    <div key={i} className="whitespace-pre-wrap break-words">
                        {renderInline(segment.content)}
                    </div>
                )
            )}
        </div>
    );
}

function CodeBlock({ code, lang }: { code: string; lang?: string }) {
    const [copied, setCopied] = useState(false);

    const copy = async () => {
        try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            // Clipboard may be unavailable (e.g. insecure context).
        }
    };

    return (
        <div className="rounded-lg border border-[var(--border)] overflow-hidden bg-[#0b0d12]">
            <div className="flex items-center justify-between px-3 py-1.5 bg-[var(--bg-elevated)] border-b border-[var(--border)]">
                <span className="text-[11px] font-mono uppercase tracking-wide text-[var(--text-muted)]">
                    {lang || "code"}
                </span>
                <button
                    type="button"
                    onClick={copy}
                    className="text-[11px] font-medium text-[var(--text-secondary)] hover:text-[var(--accent)]"
                    aria-label="Copy code"
                >
                    {copied ? "Copied!" : "Copy"}
                </button>
            </div>
            <pre className="overflow-x-auto p-3 text-[12.5px] leading-relaxed">
                <code className="font-mono text-[var(--text-primary)]">{code}</code>
            </pre>
        </div>
    );
}
