const API_BASE = ""; // Alway use relative paths for Next.js proxy

const headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer change-me-in-production",
};

export interface ChatResponse {
    response: {
        content: string;
        model: string;
    };
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

export async function sendChat(
    message: string,
    model: string = "qwen2.5",
    sessionId: string = "web-session"
): Promise<ChatResponse> {
    const resp = await fetch(`${API_BASE}/v1/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({ message, model, session_id: sessionId }),
    });

    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    return resp.json();
}

export async function getFacts(userId: string = "default"): Promise<Fact[]> {
    const resp = await fetch(
        `${API_BASE}/v1/memory/facts?user_id=${userId}`,
        { headers }
    );
    if (!resp.ok) return [];
    const data = await resp.json();
    return data.facts || [];
}

export async function getPlugins(): Promise<Plugin[]> {
    const resp = await fetch(`${API_BASE}/v1/plugins`, { headers });
    if (!resp.ok) return [];
    const data = await resp.json();
    return data.plugins || [];
}

export async function* streamChat(
    message: string,
    model: string = "qwen2.5",
    sessionId: string = "web-session"
): AsyncGenerator<string> {
    const resp = await fetch(`${API_BASE}/v1/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({ message, model, session_id: sessionId }),
    });

    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    if (!resp.body) return;

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
            if (line.startsWith("data: ")) {
                try {
                    const content = line.slice(6).trim();
                    if (!content) continue;

                    const eventData = JSON.parse(content);

                    // Handle Kimiko's StreamEvent format
                    if (eventData.event === "token" && eventData.data) {
                        yield eventData.data;
                    } else if (eventData.event === "done") {
                        return; // Stream finished
                    } else if (eventData.choices?.[0]?.delta?.content) {
                        // Fallback for OpenAI-style responses if used
                        yield eventData.choices[0].delta.content;
                    }
                } catch (e) {
                    // Skip malformed SSE lines
                }
            }
        }
    }
}

export async function getMetrics(): Promise<Record<string, number>> {
    const resp = await fetch(`${API_BASE}/metrics`);
    if (!resp.ok) return {};
    const text = await resp.text();

    const metrics: Record<string, number> = {};
    const lines = text.split("\n");

    for (const line of lines) {
        if (line.startsWith("#") || !line.trim()) continue;

        // Prometheus format: metric_name{label="val"} value
        const match = line.match(/^([a-zA-Z_][a-zA-Z0-9_]*)(?:\{.*\})?\s+(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/);
        if (match) {
            const name = match[1];
            const value = parseFloat(match[2]);
            if (!isNaN(value)) {
                metrics[name] = value;
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
    const resp = await fetch(`${API_BASE}/health`);
    if (!resp.ok) throw new Error("Offline");
    return resp.json();
}

export async function runAgent(
    goal: string,
    maxSteps: number = 5
): Promise<{ answer: string; steps: string[] }> {
    const resp = await fetch(`${API_BASE}/v1/agent/run`, {
        method: "POST",
        headers,
        body: JSON.stringify({ goal, max_steps: maxSteps }),
    });
    if (!resp.ok) throw new Error(`Agent error: ${resp.status}`);
    return resp.json();
}
