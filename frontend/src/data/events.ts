// Firewall events, as the Activity and Flow pages show them.
// They arrive from the gateway through the back end (`event: firewall` on /api/events).
// Every kind and its fields: the Events table in firewall-integration.md.

// allowed: went through. blocked: stopped by Heimdall.
// flagged: let through, but the AI second opinion thinks it looks like an injection.
// removed: hidden text Heimdall cut out of a page or email; the request itself went on
// (its own tool_call event says how), so this is not a block of the request.
export type Verdict = "allowed" | "blocked" | "flagged" | "removed";
export type ResourceId = "files" | "gmail" | "web" | "model";

export type FirewallEvent = {
  id: number;
  time: string; // "14:02:11"
  at: number; // when the back end got it, in ms (Date.now() scale). The Flow page glows only for recent ones
  agent: string; // "openclaw", "hermes", or "unknown" when the call had no known key
  resource: ResourceId | null; // null: not tied to one resource (left off the Flow graph)
  action: string; // tool name, or "messages" for a model call
  target: string;
  verdict: Verdict;
  rule: string;
  detail: string;
};

// Shared look for each verdict, used by every page. Colors match the stamp inks in index.css.
export const VERDICT_STYLE: Record<Verdict, { label: string; text: string; hex: string }> = {
  allowed: { label: "Allowed", text: "text-allowed", hex: "#9cc49f" },
  blocked: { label: "Blocked", text: "text-blocked", hex: "#cf5a52" },
  flagged: { label: "Flagged", text: "text-waiting", hex: "#d7a548" },
  removed: { label: "Removed", text: "text-waiting", hex: "#d7a548" },
};

const AGENT_NAMES: Record<string, string> = { openclaw: "OpenClaw", hermes: "Hermes" };
export const agentName = (id: string) => AGENT_NAMES[id] ?? "An unknown caller";

// files_read -> files, gmail_send -> gmail, web_fetch -> web
function resourceOf(tool: unknown): ResourceId | null {
  const prefix = String(tool ?? "").split("_")[0];
  return prefix === "files" || prefix === "gmail" || prefix === "web" ? prefix : null;
}

function hostOf(url: unknown): string {
  try {
    return new URL(String(url)).host;
  } catch {
    return String(url ?? "");
  }
}

// {"EMAIL": 3, "PHONE": 1} -> "3 EMAIL, 1 PHONE replaced with placeholders."
function placeholderNote(counts: unknown): string {
  const parts = Object.entries((counts ?? {}) as Record<string, number>)
    .filter(([, n]) => n > 0)
    .map(([type, n]) => `${n} ${type}`);
  return parts.length ? ` ${parts.join(", ")} replaced with placeholders.` : "";
}

const str = (value: unknown) => (value == null ? "" : String(value));

// The gateway path a blocked model call used -> the provider it was meant for.
// /model/local/... is Ollama, /model/messages is Anthropic's API, /model/chat/completions is Gemini's.
function providerOf(path: unknown): string {
  const p = str(path);
  if (p.includes("/local")) return "the local model";
  if (p.includes("messages")) return "Anthropic";
  if (p.includes("chat/completions")) return "Gemini";
  return p || "an AI model";
}

// One gateway event -> one feed row. null: not shown (diagnostics, and checks that found nothing).
// Text comes straight from the event's fields: no scores or made-up numbers.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function fromGateway(raw: Record<string, any>): FirewallEvent | null {
  const base = {
    id: Number(raw.id),
    time: str(raw.time).slice(11, 19),
    at: Date.parse(str(raw.time)), // local time, same computer as the back end
    agent: str(raw.agent) || "unknown",
    rule: str(raw.rule_id),
  };
  switch (raw.kind) {
    case "tool_call": {
      const allowed = raw.decision === "allow" || raw.decision === "approved";
      const byUser = raw.decision === "approved" ? "You approved it. " : raw.decision === "denied_by_user" ? "You denied it. " : "";
      return {
        ...base,
        resource: resourceOf(raw.tool),
        action: str(raw.tool),
        target: str(raw.path) || "your folders",
        verdict: allowed ? "allowed" : "blocked",
        detail: byUser + str(raw.reason) + placeholderNote(raw.placeholders),
      };
    }
    case "tool_denied":
      return { ...base, resource: resourceOf(raw.tool), action: str(raw.tool), target: "", verdict: "blocked", rule: "unknown_key", detail: str(raw.reason) };
    case "hidden_instruction":
      return {
        ...base,
        resource: resourceOf(raw.tool),
        action: str(raw.tool),
        target: str(raw.source),
        verdict: "removed",
        detail: `Hidden text (${str(raw.where)}) removed from the content before the agent saw it: "${str(raw.text)}". ${str(raw.reason)}`,
      };
    case "injection_check":
      // Only "flagged" is shown. "not_checked" means no check ran, so it must never look clean.
      if (raw.verdict !== "flagged") return null;
      return {
        ...base,
        resource: resourceOf(raw.tool),
        action: str(raw.tool),
        target: "",
        verdict: "flagged",
        rule: "injection_check",
        detail: `The AI check (${str(raw.model)}) flagged this text: "${str(raw.quote)}"`,
      };
    case "model_forwarded":
      return {
        ...base,
        resource: "model",
        action: "messages",
        target: hostOf(raw.url),
        verdict: "allowed",
        detail: `Model ${str(raw.model)}. The provider answered with status ${str(raw.status)}.`,
      };
    case "model_blocked":
      return {
        ...base,
        resource: "model",
        action: "messages",
        target: providerOf(raw.path),
        verdict: "blocked",
        rule: str(raw.rule_id) || "model_blocked",
        detail: str(raw.reason),
      };
    case "model_withheld":
      return {
        ...base,
        resource: "model",
        action: "messages",
        target: (raw.files ?? []).join(", "),
        verdict: "blocked",
        detail: "You denied consent, so the request went out without these files.",
      };
    case "consent":
      return {
        ...base,
        resource: "model",
        action: "messages",
        target: str(raw.file),
        verdict: raw.decision === "approve" ? "allowed" : "blocked",
        rule: "consent",
        detail: `Your answer on sending this Confidential file to ${str(raw.provider)}: ${raw.decision === "approve" ? "allowed" : "denied"}.`,
      };
    case "ask_failed":
      return {
        ...base,
        resource: null,
        action: "ask you",
        target: "",
        verdict: "blocked",
        rule: "ask_failed",
        detail: `A question didn't reach you, so it counted as a deny. ${str(raw.reason)}`,
      };
    default:
      // model_call (the matching model_forwarded or model_blocked follows), model_other,
      // model_error, model_upstream_error: diagnostics, see `docker compose logs gateway`.
      return null;
  }
}
