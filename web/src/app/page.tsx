"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import {
    getChatHistory,
    getModels,
    streamChat,
    type ChatMessage,
    type ModelEntry,
} from "@/lib/api";
import MessageContent from "@/components/MessageContent";
import PageHeader from "@/components/PageHeader";

const SESSION_KEY = "kimiko_session_id";
const MODEL_KEY = "kimiko_model";
const DEFAULT_MODEL = "qwen2.5";

const SUGGESTIONS = [
    "Explain how the retrieval pipeline works",
    "Write a Python function to debounce calls",
    "Summarize this into five bullet points",
];

function getOrCreateSessionId(): string {
    if (typeof window === "undefined") return uuidv4();
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
        id = uuidv4();
        localStorage.setItem(SESSION_KEY, id);
    }
    return id;
}

const WELCOME: ChatMessage = {
    role: "assistant",
    content: "Hello! I'm Kimiko, your AI assistant. How can I help you today?",
};

/** Drop a trailing empty assistant placeholder left by an aborted/failed run. */
function removeTrailingEmptyAssistant(prev: ChatMessage[]): ChatMessage[] {
    const next = [...prev];
    const last = next[next.length - 1];
    if (last && last.role === "assistant" && last.content === "") next.pop();
    return next;
}

export default function ChatPage() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [model, setModel] = useState(DEFAULT_MODEL);
    const [activeModel, setActiveModel] = useState(DEFAULT_MODEL);
    const [loading, setLoading] = useState(false);
    const [historyLoading, setHistoryLoading] = useState(true);
    const [models, setModels] = useState<ModelEntry[]>([]);
    const [sessionId, setSessionId] = useState<string>("");
    const [error, setError] = useState<string | null>(null);
    const [lastPrompt, setLastPrompt] = useState<string | null>(null);
    const [atBottom, setAtBottom] = useState(true);

    const bottomRef = useRef<HTMLDivElement>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    // Load session, saved model, model catalog, and history on mount.
    useEffect(() => {
        const sid = getOrCreateSessionId();
        setSessionId(sid);

        const savedModel = localStorage.getItem(MODEL_KEY);
        if (savedModel) setModel(savedModel);

        getModels().then((catalog) => {
            if (catalog.length === 0) return;
            setModels(catalog);
            // If the saved/default model isn't installed, fall back to one that is.
            setModel((prev) =>
                catalog.some((m) => m.id === prev)
                    ? prev
                    : (catalog.find((m) => m.available)?.id ?? catalog[0].id)
            );
        });

        setHistoryLoading(true);
        getChatHistory(sid)
            .then((history) => {
                setMessages(history.length > 0 ? history : [WELCOME]);
            })
            .finally(() => setHistoryLoading(false));
    }, []);

    // Persist the selected model.
    useEffect(() => {
        if (model) localStorage.setItem(MODEL_KEY, model);
    }, [model]);

    // Abort any in-flight stream when the page unmounts.
    useEffect(() => {
        return () => abortRef.current?.abort();
    }, []);

    // Keep the composer sized to its content.
    useEffect(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
    }, [input]);

    // Follow new tokens only when the user is already near the bottom.
    useEffect(() => {
        if (atBottom) {
            bottomRef.current?.scrollIntoView({
                behavior: loading ? "auto" : "smooth",
                block: "end",
            });
        }
    }, [messages, atBottom, loading]);

    const onScroll = () => {
        const el = scrollRef.current;
        if (!el) return;
        setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
    };

    const scrollToLatest = () => {
        setAtBottom(true);
        bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    };

    const pickSuggestion = (text: string) => {
        setInput(text);
        textareaRef.current?.focus();
    };

    const runStream = useCallback(
        async (prompt: string, appendUser: boolean) => {
            if (!prompt.trim()) return;

            setError(null);
            setLastPrompt(prompt);

            setMessages((prev) => {
                const base = removeTrailingEmptyAssistant(prev);
                const next = appendUser
                    ? [...base, { role: "user" as const, content: prompt }]
                    : base;
                return [...next, { role: "assistant" as const, content: "" }];
            });

            setLoading(true);
            setActiveModel(model);

            const controller = new AbortController();
            abortRef.current = controller;
            let full = "";

            try {
                for await (const chunk of streamChat(prompt, model, sessionId, controller.signal)) {
                    full += chunk;
                    setMessages((prev) => {
                        const next = [...prev];
                        next[next.length - 1] = { role: "assistant", content: full };
                        return next;
                    });
                }

                if (!full.trim()) {
                    setMessages((prev) => {
                        const next = [...prev];
                        next[next.length - 1] = {
                            role: "assistant",
                            content: "_(The model returned an empty response.)_",
                        };
                        return next;
                    });
                }
            } catch (err) {
                if (controller.signal.aborted) {
                    // Keep whatever streamed before the user hit Stop.
                    if (!full.trim()) setMessages(removeTrailingEmptyAssistant);
                } else {
                    const message =
                        err instanceof Error ? err.message : "Failed to reach Kimiko.";
                    setError(message);
                    if (!full.trim()) setMessages(removeTrailingEmptyAssistant);
                }
            } finally {
                setLoading(false);
                abortRef.current = null;
            }
        },
        [model, sessionId]
    );

    const handleSend = () => {
        const msg = input.trim();
        if (!msg || loading) return;
        setInput("");
        runStream(msg, true);
    };

    const handleStop = () => {
        abortRef.current?.abort();
    };

    const startNewChat = () => {
        abortRef.current?.abort();
        const newSid = uuidv4();
        localStorage.setItem(SESSION_KEY, newSid);
        setSessionId(newSid);
        setMessages([
            { role: "assistant", content: "New conversation started! How can I help you?" },
        ]);
        setInput("");
        setError(null);
        setLastPrompt(null);
        setAtBottom(true);
    };

    const selectedModel = models.find((m) => m.id === model);
    const modelUnavailable = selectedModel ? !selectedModel.available : false;
    const showSuggestions = messages.length <= 1 && !loading && !historyLoading;

    return (
        <div className="flex flex-col h-full bg-[var(--bg-primary)]">
            <PageHeader
                icon="🏯"
                title="Kimiko"
                subtitle={loading ? `${activeModel} · generating…` : activeModel}
                badge={
                    <span className="badge badge-accent hidden sm:inline-flex">Local</span>
                }
                actions={
                    <>
                        <label className="sr-only" htmlFor="model-select">
                            Model
                        </label>
                        <select
                            id="model-select"
                            value={model}
                            onChange={(e) => setModel(e.target.value)}
                            className="input-modern w-auto min-w-[150px] max-w-[220px] py-2 px-3 text-sm bg-[var(--bg-card)]"
                        >
                            {models.length > 0 ? (
                                models.map((m) => (
                                    <option key={m.id} value={m.id} disabled={!m.available}>
                                        {m.name}
                                        {m.available ? "" : " (not pulled)"}
                                    </option>
                                ))
                            ) : (
                                <>
                                    <option value="qwen2.5">Qwen 2.5</option>
                                    <option value="deepseek-r1:7b">DeepSeek R1 7B</option>
                                    <option value="codellama">CodeLlama</option>
                                    <option value="llama3.2">Llama 3.2</option>
                                </>
                            )}
                        </select>
                        <button
                            onClick={startNewChat}
                            className="btn-secondary text-sm px-3 py-2"
                            title="Start a new conversation"
                        >
                            <svg
                                aria-hidden="true"
                                className="w-4 h-4"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                                strokeWidth={2}
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                            </svg>
                            <span className="hidden sm:inline">New Chat</span>
                        </button>
                    </>
                }
            />

            {/* Messages */}
            <div className="relative flex-1 overflow-hidden">
                <div
                    ref={scrollRef}
                    onScroll={onScroll}
                    role="log"
                    aria-live="polite"
                    aria-busy={loading}
                    className="absolute inset-0 overflow-y-auto px-4 sm:px-6 py-6 space-y-5"
                >
                    {historyLoading ? (
                        <HistorySkeleton />
                    ) : messages.length === 0 ? (
                        <EmptyChat onPick={pickSuggestion} />
                    ) : (
                        messages.map((msg, i) => {
                            const isLast = i === messages.length - 1;
                            const isStreaming = loading && isLast && msg.role === "assistant";
                            const isUser = msg.role === "user";

                            return (
                                <div
                                    key={i}
                                    className={`flex gap-3 ${isUser ? "justify-end" : ""} animate-fade-up`}
                                >
                                    {!isUser && (
                                        <div
                                            aria-hidden="true"
                                            className="w-9 h-9 rounded-xl bg-[var(--accent)] flex items-center justify-center text-lg shrink-0 shadow-sm"
                                        >
                                            🏯
                                        </div>
                                    )}

                                    <div
                                        className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${isUser
                                            ? "bg-[var(--accent)] text-black rounded-br-md whitespace-pre-wrap break-words"
                                            : "bg-[var(--bg-card)] border border-[var(--border)] rounded-bl-md"
                                            }`}
                                    >
                                        {isUser ? (
                                            msg.content
                                        ) : msg.content ? (
                                            <>
                                                <MessageContent content={msg.content} />
                                                {isStreaming && (
                                                    <span
                                                        aria-hidden="true"
                                                        className="inline-block w-1.5 h-4 ml-0.5 align-middle bg-[var(--accent)] rounded-sm animate-pulse"
                                                    />
                                                )}
                                            </>
                                        ) : isStreaming ? (
                                            <TypingDots />
                                        ) : (
                                            <span className="text-[var(--text-muted)]">…</span>
                                        )}
                                    </div>

                                    {isUser && (
                                        <div
                                            aria-hidden="true"
                                            className="w-9 h-9 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border)] flex items-center justify-center text-sm shrink-0"
                                        >
                                            👤
                                        </div>
                                    )}
                                </div>
                            );
                        })
                    )}

                    {showSuggestions && (
                        <div className="flex flex-wrap gap-2 pt-1 animate-fade-in">
                            {SUGGESTIONS.map((s) => (
                                <button
                                    key={s}
                                    type="button"
                                    onClick={() => pickSuggestion(s)}
                                    className="btn-ghost text-xs border border-[var(--border)] rounded-full px-3 py-1.5"
                                >
                                    {s}
                                </button>
                            ))}
                        </div>
                    )}

                    <div ref={bottomRef} />
                </div>

                {!atBottom && (
                    <button
                        type="button"
                        onClick={scrollToLatest}
                        className="absolute bottom-4 right-4 z-10 btn-secondary text-xs px-3 py-2 shadow-lg animate-fade-in"
                    >
                        ↓ Jump to latest
                    </button>
                )}
            </div>

            {/* Error banner */}
            {error && (
                <div className="mx-4 sm:mx-6 mb-2 flex items-start gap-3 rounded-lg border border-[var(--error)]/40 bg-[var(--error)]/10 px-3 py-2.5 animate-fade-in">
                    <span aria-hidden="true" className="text-sm">
                        ⚠️
                    </span>
                    <p className="flex-1 text-xs text-[var(--text-secondary)]">
                        {error}
                        {lastPrompt && (
                            <span className="text-[var(--text-muted)]">
                                {" "}
                                Is Ollama running and the model pulled?
                            </span>
                        )}
                    </p>
                    {lastPrompt && (
                        <button
                            type="button"
                            onClick={() => runStream(lastPrompt, false)}
                            disabled={loading}
                            className="text-xs font-semibold text-[var(--accent)] hover:underline disabled:opacity-50"
                        >
                            Retry
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => setError(null)}
                        aria-label="Dismiss error"
                        className="text-[var(--text-muted)] hover:text-[var(--text-primary)] text-sm leading-none"
                    >
                        ✕
                    </button>
                </div>
            )}

            {/* Composer */}
            <div className="px-4 sm:px-6 py-3 sm:py-4 border-t border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-sm">
                {modelUnavailable && (
                    <p className="mb-2 text-xs text-[var(--warning)]">
                        This model is not pulled yet. Run{" "}
                        <code className="font-mono">ollama pull {model}</code> to enable it.
                    </p>
                )}
                <div className="flex items-end gap-2 sm:gap-3">
                    <label className="sr-only" htmlFor="chat-input">
                        Message Kimiko
                    </label>
                    <textarea
                        id="chat-input"
                        ref={textareaRef}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                                e.preventDefault();
                                handleSend();
                            }
                        }}
                        placeholder="Message Kimiko… (Shift+Enter for new line)"
                        rows={1}
                        className="flex-1 input-modern resize-none min-h-[48px] max-h-[180px] py-3 bg-[var(--bg-card)]"
                    />
                    {loading ? (
                        <button
                            type="button"
                            onClick={handleStop}
                            className="btn-danger min-h-[48px] px-4 sm:px-6 self-end"
                            title="Stop generating"
                        >
                            <span aria-hidden="true">■</span>
                            <span className="hidden sm:inline">Stop</span>
                        </button>
                    ) : (
                        <button
                            type="button"
                            onClick={handleSend}
                            disabled={!input.trim()}
                            className="btn-primary min-h-[48px] px-4 sm:px-6 self-end"
                        >
                            <span className="hidden sm:inline">Send</span>
                            <svg
                                aria-hidden="true"
                                className="w-4 h-4 sm:hidden"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                                strokeWidth={2}
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 6l6 6-6 6" />
                            </svg>
                        </button>
                    )}
                </div>
                <p className="text-[11px] text-[var(--text-muted)] text-right mt-2 hidden sm:block">
                    Enter to send • Shift+Enter for new line
                </p>
            </div>
        </div>
    );
}

function TypingDots() {
    return (
        <div className="flex gap-1 py-1" aria-label="Kimiko is typing">
            {[0, 1, 2].map((i) => (
                <span
                    key={i}
                    className="w-2 h-2 rounded-full bg-[var(--accent)] animate-blink"
                    style={{ animationDelay: `${i * 150}ms` }}
                />
            ))}
        </div>
    );
}

function HistorySkeleton() {
    return (
        <div className="space-y-5" aria-label="Restoring conversation">
            {[0, 1, 2].map((i) => (
                <div
                    key={i}
                    className={`flex gap-3 ${i % 2 === 0 ? "" : "justify-end"}`}
                >
                    <div
                        className="skeleton h-16"
                        style={{ width: `${45 + (i % 3) * 10}%` }}
                    />
                </div>
            ))}
        </div>
    );
}

function EmptyChat({ onPick }: { onPick: (text: string) => void }) {
    return (
        <div className="flex flex-col items-center justify-center h-full text-center">
            <div
                aria-hidden="true"
                className="w-16 h-16 rounded-2xl bg-[var(--accent-muted)] flex items-center justify-center text-3xl mb-4"
            >
                🏯
            </div>
            <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">
                Welcome to Kimiko
            </h3>
            <p className="text-[var(--text-muted)] text-sm max-w-xs">
                Start a conversation or pick a prompt below.
            </p>
            <div className="flex flex-wrap justify-center gap-2 mt-4 max-w-md">
                {SUGGESTIONS.map((s) => (
                    <button
                        key={s}
                        type="button"
                        onClick={() => onPick(s)}
                        className="btn-ghost text-xs border border-[var(--border)] rounded-full px-3 py-1.5"
                    >
                        {s}
                    </button>
                ))}
            </div>
        </div>
    );
}
