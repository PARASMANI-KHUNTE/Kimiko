const API_BASE = ""; // Always use relative paths for Next.js proxy

const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "change-me-in-production";

const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${API_KEY}`,
};

export interface ChatResponse {
    id: string;
    message: {
        role: "system" | "user" | "assistant";
        content: string;
    };
    model: string;
    intent?: string | null;
    session_id?: string;
    usage?: {
        prompt_tokens: number;
        completion_tokens: number;
        total_tokens: number;
    } | null;
    created_at?: string;
}

export interface ChatMessage {
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
}

export interface ModelEntry {
    id: string;
    name: string;
    type: string;
    available: boolean;
}

export interface Fact {
    category: string;
    fact: string;
    confidence: number;
}

export interface Plugin {
    name: string;
    version: string;
    author: string;
    capabilities: string[];
}

/** Read a useful error message out of a failed response. */
async function describeError(resp: Response): Promise<string> {
    try {
        const data = await resp.json();
        if (typeof data?.detail === "string") return data.detail;
        if (typeof data?.message === "string") return data.message;
    } catch {
        // Fall through to the status line below.
    }
    return `Request failed (${resp.status} ${resp.statusText})`;
}

/**
 * Fetch with an optional timeout. A caller-provided signal still wins, so
 * cancellation (e.g. "Stop generating") keeps working.
 */
async function fetchWithTimeout(
    input: RequestInfo | URL,
    init: RequestInit = {},
    timeoutMs = 15_000
): Promise<Response> {
    const controller = new AbortController();
    const external = init.signal;
    const onAbort = () => controller.abort();
    external?.addEventListener("abort", onAbort);

    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(input, { ...init, signal: controller.signal });
    } finally {
        clearTimeout(timer);
        external?.removeEventListener("abort", onAbort);
    }
}

export async function sendChat(
    message: string,
    model: string = "qwen3.5:4b",
    sessionId: string = "web-session"
): Promise<ChatResponse> {
    const resp = await fetchWithTimeout(`${API_BASE}/v1/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({ message, model, session_id: sessionId }),
    });

    if (!resp.ok) throw new Error(await describeError(resp));
    return resp.json();
}

export async function getChatHistory(sessionId: string): Promise<ChatMessage[]> {
    try {
        const resp = await fetchWithTimeout(
            `${API_BASE}/v1/chat/history/${encodeURIComponent(sessionId)}`,
            { headers }
        );
        if (!resp.ok) return [];
        const data = await resp.json();
        return Array.isArray(data.messages) ? (data.messages as ChatMessage[]) : [];
    } catch {
        return [];
    }
}

export async function getModels(): Promise<ModelEntry[]> {
    try {
        const resp = await fetchWithTimeout(`${API_BASE}/v1/models/catalog`, { headers });
        if (!resp.ok) return [];
        const data = await resp.json();
        return Array.isArray(data.models) ? (data.models as ModelEntry[]) : [];
    } catch {
        return [];
    }
}

export async function getFacts(userId: string = "default"): Promise<Fact[]> {
    const resp = await fetchWithTimeout(
        `${API_BASE}/v1/memory/facts?user_id=${encodeURIComponent(userId)}`,
        { headers }
    );
    if (!resp.ok) throw new Error(await describeError(resp));
    const data = await resp.json();
    return Array.isArray(data.facts) ? (data.facts as Fact[]) : [];
}

export async function getPlugins(): Promise<Plugin[]> {
    const resp = await fetchWithTimeout(`${API_BASE}/v1/plugins`, { headers });
    if (!resp.ok) throw new Error(await describeError(resp));
    const data = await resp.json();
    return Array.isArray(data.plugins) ? (data.plugins as Plugin[]) : [];
}

type ParsedSse =
    | { token: string }
    | { done: true }
    | { error: string }
    | null;

/**
 * Parse one SSE event block (the text between blank lines).
 *
 * The backend sends frames like:
 *   data: {"event":"token","data":"Hel"}
 *
 * Older/OpenAI-compatible frames (`choices[0].delta.content`) are supported
 * too, and `[DONE]` terminates the stream.
 */
function parseSseEvent(raw: string): ParsedSse {
    const dataLines = raw
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).replace(/^ /, ""));

    if (dataLines.length === 0) return null;

    const payload = dataLines.join("\n").trim();
    if (!payload) return null;
    if (payload === "[DONE]") return { done: true };

    try {
        const obj = JSON.parse(payload);

        if (obj?.event === "token") {
            return typeof obj.data === "string" && obj.data.length > 0
                ? { token: obj.data }
                : null;
        }
        if (obj?.event === "done") return { done: true };
        if (obj?.event === "error") {
            return { error: typeof obj.data === "string" ? obj.data : "Stream error" };
        }

        const delta = obj?.choices?.[0]?.delta?.content;
        if (typeof delta === "string" && delta.length > 0) return { token: delta };

        return null;
    } catch {
        // Ignore keep-alives / malformed frames instead of killing the stream.
        return null;
    }
}

export async function* streamChat(
    message: string,
    model: string = "qwen3.5:4b",
    sessionId: string = "web-session",
    signal?: AbortSignal
): AsyncGenerator<string> {
    const resp = await fetch(`${API_BASE}/v1/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({ message, model, session_id: sessionId }),
        signal,
    });

    if (!resp.ok) throw new Error(await describeError(resp));
    if (!resp.body) return;

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            // Normalise CRLF so a single separator check covers both styles.
            buffer = buffer.replace(/\r\n/g, "\n");

            // Frames are separated by a blank line. A network chunk can split a
            // frame in half, so keep the tail buffered until the next read.
            let boundary = buffer.indexOf("\n\n");
            while (boundary !== -1) {
                const raw = buffer.slice(0, boundary);
                buffer = buffer.slice(boundary + 2);

                const event = parseSseEvent(raw);
                if (event && "done" in event) return;
                if (event && "error" in event) throw new Error(event.error);
                if (event && "token" in event) yield event.token;

                boundary = buffer.indexOf("\n\n");
            }
        }

        // Flush whichever bytes are still pending in the decoder.
        buffer += decoder.decode();
        if (buffer.trim()) {
            const event = parseSseEvent(buffer);
            if (event && "error" in event) throw new Error(event.error);
            if (event && "token" in event) yield event.token;
        }
    } finally {
        reader.releaseLock();
    }
}

export async function getMetrics(): Promise<Record<string, number>> {
    // The dashboard page itself lives at /metrics, so the proxy exposes the
    // Prometheus scrape endpoint at /api/metrics instead.
    const resp = await fetchWithTimeout(`${API_BASE}/api/metrics`);
    if (!resp.ok) return {};
    const text = await resp.text();

    const metrics: Record<string, number> = {};
    const lines = text.split("\n");

    for (const line of lines) {
        if (line.startsWith("#") || !line.trim()) continue;

        const match = line.match(
            /^([a-zA-Z_][a-zA-Z0-9_]*)(?:\{.*\})?\s+(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/
        );
        if (match) {
            const name = match[1];
            const value = parseFloat(match[2]);
            if (!Number.isNaN(value)) {
                // Counters with labels repeat the same name once per label set;
                // sum them so the dashboard shows the true total.
                metrics[name] = (metrics[name] ?? 0) + value;
            }
        }
    }

    return metrics;
}

export async function checkHealth(): Promise<{
    status: string;
    version: string;
    services: Record<string, string>;
}> {
    const resp = await fetchWithTimeout(`${API_BASE}/health`, {}, 8000);
    if (!resp.ok) throw new Error("Offline");
    return resp.json();
}

export async function runAgent(
    goal: string,
    maxSteps: number = 5,
    signal?: AbortSignal
): Promise<{ answer: string; steps: string[] }> {
    const resp = await fetch(`${API_BASE}/v1/agent/run`, {
        method: "POST",
        headers,
        body: JSON.stringify({ goal, max_steps: maxSteps }),
        signal,
    });
    if (!resp.ok) throw new Error(await describeError(resp));
    return resp.json();
}
