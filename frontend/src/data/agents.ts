// MOCK DATA: stands in for the backend until /launch and an agents list endpoint exist.

export type AgentStatus = "stopped" | "sealing" | "running";

export type Agent = {
  id: string;
  name: string;
  description: string;
  tools: string[];
  folders: string[];
  status: AgentStatus;
};

export const MOCK_AGENTS: Agent[] = [
  {
    id: "openclaw",
    name: "OpenClaw",
    description: "General-purpose assistant with skills and MCP tools.",
    tools: ["files_read", "files_list"],
    folders: ["~/Documents/notes"],
    status: "stopped",
  },
  {
    id: "hermes",
    name: "Hermes",
    description: "Inbox and messaging agent.",
    tools: ["gmail_read", "gmail_draft"],
    folders: [],
    status: "stopped",
  },
];
