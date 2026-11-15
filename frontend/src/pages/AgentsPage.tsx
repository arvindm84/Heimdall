import { Plus } from "lucide-react";
import type { Agent } from "../data/agents";
import { TOOL_NAME } from "../data/tools";

type Props = {
  agents: Agent[];
  onStart: (id: string) => void;
  onStop: (id: string) => void;
};

const STATUS = {
  stopped: { label: "Off", dot: "bg-lichen/50" },
  sealing: { label: "Starting", dot: "bg-waiting animate-pulse" },
  running: { label: "Running", dot: "bg-allowed" },
} as const;

export default function AgentsPage({ agents, onStart, onStop }: Props) {
  return (
    <div>
      <h1 className="text-3xl font-bold">Your agents</h1>
      <p className="mt-2 max-w-[62ch] text-lichen">
        Each agent runs sealed off from your computer. It can only reach your files and the internet through Heimdall,
        and only what you allow below.
      </p>

      {/* Roster: one row per agent */}
      <ul className="mt-10 border-t border-rule">
        {agents.map((agent) => (
          <li key={agent.id} className="grid grid-cols-[1fr_auto] items-start gap-x-8 gap-y-3 border-b border-rule py-7">
            <div>
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
                <dd>{agent.tools.length ? agent.tools.map((t) => TOOL_NAME[t] ?? t).join(", ") : "Nothing yet"}</dd>
                <dt className="text-lichen">Folders</dt>
                <dd>
                  {agent.folders.length ? (
                    agent.folders.map((f) => <span key={f} className="font-mono text-[13px]">{f}</span>)
                  ) : (
                    <span className="text-lichen">None</span>
                  )}
                </dd>
              </dl>
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
              <button
                onClick={() => agent.status === "stopped" && onStart(agent.id)}
                disabled={agent.status === "sealing"}
                className="min-w-28 rounded bg-paper px-4 py-2 text-sm font-bold text-ground transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
              >
                {agent.status === "stopped" ? "Start" : agent.status === "sealing" ? "Starting…" : "Open chat"}
              </button>
            </div>
          </li>
        ))}
      </ul>

      <button className="mt-6 flex items-center gap-2 text-lichen transition-colors hover:text-paper">
        <Plus className="size-4" /> Add an agent
      </button>
    </div>
  );
}
