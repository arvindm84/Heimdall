import { useState } from "react";
import { SAMPLE_EVENTS, VERDICT_STYLE, type FirewallEvent, type Verdict } from "../data/sample";
import { TOOL_VERB } from "../data/tools";

const AGENT_NAME = { openclaw: "OpenClaw", hermes: "Hermes" } as const;
const FILTERS: { id: "all" | Verdict; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "allowed", label: "Allowed" },
  { id: "blocked", label: "Blocked" },
];

// "OpenClaw wanted to read ~/.env"
function Sentence({ e }: { e: FirewallEvent }) {
  return (
    <>
      <span className="font-bold">{AGENT_NAME[e.agent]}</span> wanted to {TOOL_VERB[e.action] ?? e.action}{" "}
      <span className="break-all font-mono text-[13px]">{e.target}</span>
    </>
  );
}

export default function ActivityPage() {
  const [filter, setFilter] = useState<"all" | Verdict>("all");

  const newestFirst = [...SAMPLE_EVENTS].reverse();
  const waiting = newestFirst.filter((e) => e.verdict === "waiting");
  const history = newestFirst.filter((e) => e.verdict !== "waiting" && (filter === "all" || e.verdict === filter));
  const count = (v: Verdict) => SAMPLE_EVENTS.filter((e) => e.verdict === v).length;

  return (
    <div>
      <h1 className="text-3xl font-bold">Activity</h1>
      <p className="mt-2 text-lichen">
        Sample data. Today Heimdall allowed <span className="text-allowed">{count("allowed")}</span> requests and blocked{" "}
        <span className="text-blocked">{count("blocked")}</span>.
      </p>

      {/* Requests that need the user come first */}
      {waiting.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-bold">Needs your answer</h2>
          <ul className="mt-4 flex flex-col gap-3">
            {waiting.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-md border border-waiting/40 bg-raised px-5 py-4">
                <div className="min-w-0 flex-1">
                  <p><Sentence e={e} /></p>
                  <p className="mt-1 text-sm text-lichen">{e.detail}</p>
                </div>
                <div className="flex gap-2">
                  <button className="rounded border border-rule px-4 py-2 text-sm transition-colors hover:border-blocked hover:text-blocked">
                    Deny
                  </button>
                  <button className="rounded bg-paper px-4 py-2 text-sm font-bold text-ground hover:opacity-90">Allow once</button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-12">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 className="text-xl font-bold">History</h2>
          <div className="flex gap-4 text-sm">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={filter === f.id ? "text-paper underline underline-offset-4" : "text-lichen hover:text-paper"}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Ledger: time, what happened, why, stamp */}
        <ol className="mt-4 border-t border-rule">
          {history.map((e) => (
            <li key={e.id} className="grid grid-cols-[4.5rem_1fr_6.5rem] items-start gap-x-6 border-b border-rule py-4">
              <span className="tabular pt-0.5 text-sm text-lichen">{e.time.slice(0, 5)}</span>
              <div className="min-w-0">
                <p><Sentence e={e} /></p>
                <p className="mt-1 text-sm text-lichen">{e.detail}</p>
              </div>
              <span className={`stamp justify-self-end ${VERDICT_STYLE[e.verdict].text}`}>{VERDICT_STYLE[e.verdict].label}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
