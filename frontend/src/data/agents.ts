import type { ChatLogin, LaunchConfig } from "../lib/api";

// The agents Heimdall can run. Names must match agents/manager.py AGENTS.
// `config` is what Start sends to /api/launch until there's a permissions screen.
// The gateway only offers files_read and files_list so far.

export type AgentStatus = "stopped" | "starting" | "running" | "stopping";

export type AgentProfile = {
  id: string;
  name: string;
  description: string;
  config: LaunchConfig;
};

export type Agent = AgentProfile & {
  status: AgentStatus;
  chat: ChatLogin | null; // set while running
  error: { message: string; detail?: string } | null; // last failed action
};

export const AGENT_PROFILES: AgentProfile[] = [
  {
    id: "openclaw",
    name: "OpenClaw",
    description: "General-purpose assistant with skills and MCP tools.",
    config: { tools: ["files_read", "files_list"], provider: "gemini" },
  },
  {
    id: "hermes",
    name: "Hermes",
    description: "Assistant from Nous Research that can keep memory between chats.",
    config: { tools: ["files_read", "files_list"], provider: "gemini" },
  },
];
