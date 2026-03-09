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

  // Model type badge colors
  const typeBadge: Record<string, string> = {
    chat: "bg-violet-500/20 text-violet-300",
    code: "bg-blue-500/20 text-blue-300",
    reasoning: "bg-emerald-500/20 text-emerald-300",
    vision: "bg-amber-500/20 text-amber-300",
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-7 py-4 border-b border-gray-800">
        <div className="flex flex-col">
          <h2 className="text-lg font-semibold">💬 Chat with Kimiko</h2>
          <span className="text-xs text-gray-500 mt-0.5">
            Active: <span className="text-violet-400 font-medium">{activeModel}</span>
            {sessionId && (
              <span className="ml-3 text-gray-600 font-mono text-[10px]">
                Session: {sessionId.slice(0, 8)}…
              </span>
            )}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Model selector */}
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-violet-500"
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
            className="bg-[#1a1a2e] border border-gray-700 hover:border-violet-500 rounded-lg px-3 py-1.5 text-sm text-gray-400 hover:text-violet-400 transition-all"
            title="Start a new conversation"
          >
            ✚ New Chat
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-7 py-6 space-y-4">
        {historyLoading ? (
          <div className="flex justify-center py-10">
            <span className="text-gray-500 text-sm animate-pulse">Restoring conversation…</span>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`flex gap-3 animate-fade-in ${msg.role === "user" ? "justify-end" : ""}`}
            >
              {msg.role === "assistant" && (
                <div className="w-9 h-9 rounded-full bg-[#1a1a2e] flex items-center justify-center text-lg shrink-0">
                  🏯
                </div>
              )}
              <div
                className={`max-w-[75%] px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap ${msg.role === "user"
                    ? "bg-gradient-to-r from-violet-600 to-purple-500 text-white"
                    : "bg-[#1a1a2e] border border-gray-800"
                  }`}
              >
                {msg.content}
              </div>
              {msg.role === "user" && (
                <div className="w-9 h-9 rounded-full bg-violet-600 flex items-center justify-center text-sm shrink-0">
                  👤
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="flex gap-3 animate-fade-in">
            <div className="w-9 h-9 rounded-full bg-[#1a1a2e] flex items-center justify-center text-lg shrink-0">
              🏯
            </div>
            <div className="bg-[#1a1a2e] border border-gray-800 px-4 py-3 rounded-xl text-sm">
              <span className="inline-flex gap-1">
                <span className="w-2 h-2 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-2 h-2 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-2 h-2 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-7 py-4 border-t border-gray-800 bg-[#111118] flex gap-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Type your message… (Shift+Enter for newline)"
          rows={1}
          className="flex-1 bg-[#16162a] border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-100 outline-none resize-none focus:border-violet-500 focus:shadow-[0_0_0_3px_rgba(108,99,255,0.3)] transition-all"
        />
        <button
          onClick={handleSend}
          disabled={loading}
          className="bg-gradient-to-r from-violet-600 to-purple-500 text-white px-6 py-3 rounded-xl font-semibold text-sm hover:scale-[1.02] hover:shadow-[0_4px_16px_rgba(108,99,255,0.3)] active:scale-[0.98] transition-all disabled:opacity-50"
        >
          {loading ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
