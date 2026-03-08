"use client";

import { useState, useRef, useEffect } from "react";
import { sendChat } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Hello! I'm Kimiko, your AI assistant. How can I help you today?" },
  ]);
  const [input, setInput] = useState("");
  const [model, setModel] = useState("qwen2.5");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    setLoading(true);

    // Initial empty assistant message for streaming
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const { streamChat } = await import("@/lib/api");
      let fullContent = "";

      for await (const chunk of streamChat(msg, model)) {
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
          content: "❌ Error: Failed to stream response from Kimiko.",
        };
        return newMsgs;
      });
    }

    setLoading(false);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-7 py-5 border-b border-gray-800">
        <h2 className="text-lg font-semibold">💬 Chat with Kimiko</h2>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-violet-500"
        >
          <option value="qwen2.5">Qwen 2.5</option>
          <option value="codellama">CodeLlama</option>
          <option value="llama3.2">Llama 3.2</option>
        </select>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-7 py-6 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 animate-fade-in ${msg.role === "user" ? "justify-end" : ""
              }`}
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
        ))}
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
          placeholder="Type your message..."
          rows={1}
          className="flex-1 bg-[#16162a] border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-100 outline-none resize-none focus:border-violet-500 focus:shadow-[0_0_0_3px_rgba(108,99,255,0.3)] transition-all"
        />
        <button
          onClick={handleSend}
          disabled={loading}
          className="bg-gradient-to-r from-violet-600 to-purple-500 text-white px-6 py-3 rounded-xl font-semibold text-sm hover:scale-[1.02] hover:shadow-[0_4px_16px_rgba(108,99,255,0.3)] active:scale-[0.98] transition-all disabled:opacity-50"
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}
