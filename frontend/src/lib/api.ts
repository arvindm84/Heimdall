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
  provider?: "gemini" | "anthropic" | "local";
  model?: string;
};

// Folder access, from the popup before an agent's first start.
export type Label = "public" | "private" | "confidential";
export type Folder = { name: string; path: string };
// Only the folders the user clicked: these are the ones shared with the agent.
// Others show their nearest clicked parent's label, else confidential, and are not shared by themselves.
export type FolderLabels = Record<string, Label>;

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
  // Subfolders of a folder (leave out path for the home folder). 403 if the system won't open it.
  folders: (path?: string) =>
    call<{ path: string; folders: Folder[] }>(`/folders${path ? `?path=${encodeURIComponent(path)}` : ""}`),
  // An agent's saved folder labels; null if the user hasn't been asked yet.
  folderLabels: (agent: string) => call<{ labels: FolderLabels | null }>(`/folder-labels?agent=${agent}`),
  saveFolderLabels: (agent: string, labels: FolderLabels) => call<void>("/folder-labels", { agent, labels }),
  // The user's answer to a firewall question. 404 if it already timed out.
  // scope, only with an approve on a consent question: "once" (this file) or "folder" (every file in it).
  respond: (request_id: string, decision: "approve" | "deny", scope?: "once" | "folder") =>
    call<{ status: string }>("/response", scope ? { request_id, decision, scope } : { request_id, decision }),
};
