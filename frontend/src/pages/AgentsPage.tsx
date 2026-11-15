import { useState } from "react";
import { Plus } from "lucide-react";
import type { Agent } from "../data/agents";
import { TOOL_NAME } from "../data/tools";

type Props = {
  agents: Agent[];
  backendError: string | null;
  onStart: (id: string) => void;
  onStop: (id: string) => void;
};

const STATUS = {
  stopped: { label: "Off", dot: "bg-lichen/50" },
  starting: { label: "Starting", dot: "bg-waiting animate-pulse" },
  running: { label: "Running", dot: "bg-allowed" },
  stopping: { label: "Stopping", dot: "bg-lichen animate-pulse" },
} as const;

export default function AgentsPage({ agents, backendError, onStart, onStop }: Props) {
  return (
    <div>
      <h1 className="text-3xl font-bold">Your agents</h1>
      <p className="mt-2 max-w-[62ch] text-lichen">
        Each agent runs sealed off from your computer. It can only reach your files and the internet through Heimdall,
        and only what you allow below.
      </p>

      {backendError && (
        <p className="mt-6 rounded-md border border-blocked/50 bg-raised px-4 py-3 text-sm text-blocked">{backendError}</p>
      )}

      {/* Roster: one row per agent */}
      <ul className="mt-10 border-t border-rule">
        {agents.map((agent) => {
          const folders = agent.config.folders ?? [];
          const tools = agent.config.tools ?? [];
          return (
            <li key={agent.id} className="grid grid-cols-[1fr_auto] items-start gap-x-8 gap-y-3 border-b border-rule py-7">
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <h2 className="text-2xl font-bold">{agent.name}</h2>
                  <span className="flex items-center gap-2 text-sm text-lichen">
                    <span className={`size-2 rounded-full ${STATUS[agent.status].dot}`} />
                    {STATUS[agent.status].label}
                  </span>
                </div>
                <p className="mt-1 text-lichen">{agent.description}</p>

                {/* What the firewall lets it touch, in plain words */}
                <dl className="mt-4 grid grid-cols-[6rem_1fr] gap-y-1 text-sm">
                  <dt className="text-lichen">Can</dt>
                  <dd>{tools.length ? tools.map((t) => TOOL_NAME[t] ?? t).join(", ") : "Nothing yet"}</dd>
                  <dt className="text-lichen">Folders</dt>
                  <dd>
                    {folders.length ? (
                      folders.map((f) => <div key={f.path} className="font-mono text-[13px]">{f.path}</div>)
                    ) : (
                      <span className="text-lichen">None</span>
                    )}
                  </dd>
                </dl>

                {agent.status === "starting" && (
                  <p className="mt-4 text-sm text-waiting">
                    Building and sealing the container. The first start can take a few minutes.
                  </p>
                )}

                {/* The chat opens in the browser, which asks for this login. */}
                {agent.status === "running" && agent.chat && (
                  <dl className="mt-4 grid grid-cols-[6rem_1fr] items-center gap-y-1.5 text-sm">
                    <dt className="text-lichen">Chat login</dt>
                    <dd className="text-lichen">Your browser will ask for these when the chat opens.</dd>
                    <dt className="text-lichen">Username</dt>
                    <dd><CopyField value={agent.chat.chat_user} /></dd>
                    <dt className="text-lichen">Password</dt>
                    <dd><CopyField value={agent.chat.chat_token} /></dd>
                  </dl>
                )}

                {agent.error && (
                  <div className="mt-4 text-sm text-blocked">
                    <p>{agent.error.message}</p>
                    {agent.error.detail && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-lichen hover:text-paper">Show details</summary>
                        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-raised p-3 font-mono text-xs text-lichen">
                          {agent.error.detail}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
              </div>

              <div className="flex gap-2 pt-1">
                {agent.status === "running" && (
                  <button
                    onClick={() => onStop(agent.id)}
                    className="rounded border border-rule px-4 py-2 text-sm text-lichen transition-colors hover:border-lichen hover:text-paper"
                  >
                    Stop
                  </button>
                )}
                {agent.status === "running" && agent.chat ? (
                  // target="_blank": a new browser tab in development; the system browser in the desktop app.
                  <a
                    href={agent.chat.chat_url}
                    target="_blank"
                    rel="noreferrer"
                    className="min-w-28 rounded bg-paper px-4 py-2 text-center text-sm font-bold text-ground transition-opacity hover:opacity-90"
                  >
                    Open chat
                  </a>
                ) : (
                  <button
                    onClick={() => onStart(agent.id)}
                    disabled={agent.status !== "stopped"}
                    className="min-w-28 rounded bg-paper px-4 py-2 text-sm font-bold text-ground transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
                  >
                    {agent.status === "starting" ? "Starting…" : agent.status === "stopping" ? "Stopping…" : "Start"}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <button className="mt-6 flex items-center gap-2 text-lichen transition-colors hover:text-paper">
        <Plus className="size-4" /> Add an agent
      </button>
    </div>
  );
}

// A value in monospace with a Copy button that confirms for a moment.
function CopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <span className="flex flex-wrap items-center gap-3">
      <span className="break-all font-mono text-[13px]">{value}</span>
      <button onClick={copy} className="text-xs text-lichen underline underline-offset-2 hover:text-paper">
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}
