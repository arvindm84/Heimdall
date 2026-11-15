// Calls to the Flask back end. All routes live under /api (see backend/app.py).

// How to reach a running agent's chat. The user types chat_user / chat_token into the browser's login prompt.
export type ChatLogin = { agent: string; chat_url: string; chat_user: string; chat_token: string };

// What /api/launch accepts as "config" (every field optional).
export type LaunchConfig = {
  tools?: string[];
  folders?: { path: string; label: "public" | "private" | "confidential"; write?: boolean }[];
  skills?: string[]; // OpenClaw only
  memory?: boolean; // Hermes only
  delegation?: boolean; // Hermes only
  provider?: "gemini" | "anthropic";
  model?: string;
};

type AgentsResponse = {
  agents: { name: string; chat: ChatLogin | null }[];
  providers: { name: string; default_model: string }[];
};

// A failed call, with the back end's message and (for Docker failures) its longer detail.
export class ApiError extends Error {
  detail?: string;
  constructor(message: string, detail?: string) {
    super(message);
    this.detail = detail;
  }
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Can't reach the Heimdall back end. Is it running?");
  }
  const text = await res.text();
  const data = (() => {
    try {
      return JSON.parse(text);
    } catch {
      return {};
    }
  })();
  if (!res.ok) {
    // In development, Vite answers with an empty 500 when Flask isn't running.
    if (!text) throw new ApiError("Can't reach the Heimdall back end. Is it running?");
    throw new ApiError(data.error ?? `Request failed (${res.status})`, data.detail);
  }
  return data as T;
}

export const api = {
  agents: () => call<AgentsResponse>("/agents"),
  // Slow: answers once the agent's chat is up (minutes on the first build).
  launch: (agent: string, config: LaunchConfig) => call<ChatLogin>("/launch", { agent, config }),
  stop: (agent: string) => call<{ status: string }>("/stop", { agent }),
  kill: (agent: string) => call<{ status: string }>("/kill", { agent }),
  // The user's answer to a firewall question. 404 if it already timed out.
  respond: (request_id: string, decision: "approve" | "deny") =>
    call<{ status: string }>("/response", { request_id, decision }),
};
