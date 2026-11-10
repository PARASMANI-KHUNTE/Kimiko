"use client";

import { useState, useRef, useEffect } from "react";
import { streamChat, getChatHistory, getModels, ModelEntry, ChatMessage } from "@/lib/api";
import { v4 as uuidv4 } from "uuid";

const SESSION_KEY = "kimiko_session_id";
const DEFAULT_MODEL = "qwen2.5";

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return uuidv4();
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = uuidv4();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
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
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load session ID and history on mount
  useEffect(() => {
    const sid = getOrCreateSessionId();
    setSessionId(sid);

    // Load models catalog
    getModels().then((catalog) => {
      if (catalog.length > 0) setModels(catalog);
    });

    // Restore history from backend
    setHistoryLoading(true);
    getChatHistory(sid).then((history) => {
      if (history.length > 0) {
        setMessages(history);
      } else {
        setMessages([
          { role: "assistant", content: "Hello! I'm Kimiko, your AI assistant. How can I help you today?" },
        ]);
      }
      setHistoryLoading(false);
    });
  }, []);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const startNewChat = () => {
    const newSid = uuidv4();
    localStorage.setItem(SESSION_KEY, newSid);
    setSessionId(newSid);
    setMessages([
      { role: "assistant", content: "New conversation started! How can I help you?" },
    ]);
  };

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    setLoading(true);

    // Initial empty assistant message for streaming
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const { streamChat: doStream } = await import("@/lib/api");
      let fullContent = "";
      setActiveModel(model);

      for await (const chunk of doStream(msg, model, sessionId)) {
        fullContent += chunk;
        setMessages((prev) => {
          const newMsgs = [...prev];
          newMsgs[newMsgs.length - 1] = {
            role: "assistant",
            content: fullContent,
          };
          return newMsgs;
        });
      }
    } catch (e) {
      console.error("Streaming error:", e);
      setMessages((prev) => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1] = {
          role: "assistant",
          content: "❌ Error: Failed to stream response from Kimiko. Make sure the model is pulled in Ollama.",
        };
        return newMsgs;
      });
    }

    setLoading(false);
  };

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[var(--accent)] flex items-center justify-center text-lg">
            🏯
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Kimiko</h2>
            <span className="text-xs text-[var(--text-muted)] font-medium">{activeModel}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Model selector */}
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="input-modern w-auto min-w-[180px] py-2 px-3 text-sm bg-[var(--bg-card)]"
          >
            {models.length > 0 ? (
              models.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.available}>
                  {m.name}{m.available ? "" : " (not pulled)"}
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
          {/* New Chat button */}
          <button
            onClick={startNewChat}
            className="btn-secondary text-sm px-3 py-2"
            title="Start a new conversation"
          >
            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New Chat
          </button>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {historyLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-[var(--text-muted)]">
              <div className="w-12 h-12 rounded-full border-3 border-[var(--border)] border-t-[var(--accent)] animate-spin mx-auto mb-4" />
              <p className="text-sm">Restoring conversation…</p>
            </div>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-[var(--accent-muted)] flex items-center justify-center text-3xl mb-4">
              🏯
            </div>
            <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">Welcome to Kimiko</h3>
            <p className="text-[var(--text-muted)] text-sm max-w-xs">Start a conversation or select a model to begin.</p>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""} animate-in fade-in slide-y-2 duration-200`}
            >
              {msg.role === "assistant" && (
                <div className="w-9 h-9 rounded-xl bg-[var(--accent)] flex items-center justify-center text-lg shrink-0 shadow-sm">
                  🏯
                </div>
              )}
              <div
                className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${msg.role === "user"
                    ? "bg-[var(--accent)] text-black rounded-br-md"
                    : "bg-[var(--bg-card)] border border-[var(--border)] rounded-bl-md"
                  }`}
              >
                {msg.content}
              </div>
              {msg.role === "user" && (
                <div className="w-9 h-9 rounded-xl bg-[var(--accent)] flex items-center justify-center text-sm shrink-0 shadow-sm">
                  👤
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="flex gap-3 animate-in fade-in slide-y-2 duration-200">
            <div className="w-9 h-9 rounded-xl bg-[var(--accent)] flex items-center justify-center text-lg shrink-0 shadow-sm">
              🏯
            </div>
            <div className="bg-[var(--bg-card)] border border-[var(--border)] px-4 py-3 rounded-2xl rounded-bl-md text-sm">
              <div className="flex gap-1">
                <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-sm">
        <div className="flex gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Message Kimiko… (Shift+Enter for new line)"
            rows={1}
            className="flex-1 input-modern resize-none min-h-[48px] bg-[var(--bg-card)]"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="btn-primary px-6 py-3 min-h-[48px] self-end"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                Sending…
              </span>
            ) : (
              "Send"
            )}
          </button>
        </div>
        <p className="text-xs text-[var(--text-muted)] text-right mt-2">Press Enter to send • Shift+Enter for new line</p>
      </div>
    </div>
  );
}
