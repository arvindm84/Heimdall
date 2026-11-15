import { useState } from "react";
import QuestionCard from "../components/QuestionCard";
import { VERDICT_STYLE, agentName, type FirewallEvent, type Verdict } from "../data/events";
import { TOOL_VERB } from "../data/tools";
import type { Question } from "../lib/live";

const FILTERS: { id: "all" | Verdict; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "allowed", label: "Allowed" },
  { id: "blocked", label: "Blocked" },
  { id: "flagged", label: "Flagged" },
  { id: "removed", label: "Removed" },
];

type Props = { events: FirewallEvent[]; questions: Question[]; connected: boolean };

// "OpenClaw wanted to read docs/plan.md"
function Sentence({ e }: { e: FirewallEvent }) {
  return (
    <>
      <span className="font-bold">{agentName(e.agent)}</span> wanted to {TOOL_VERB[e.action] ?? e.action}{" "}
      <span className="break-all font-mono text-[13px]">{e.target}</span>
    </>
  );
}

export default function ActivityPage({ events, questions, connected }: Props) {
  const [filter, setFilter] = useState<"all" | Verdict>("all");

  const history = [...events].reverse().filter((e) => filter === "all" || e.verdict === filter);
  const count = (v: Verdict) => events.filter((e) => e.verdict === v).length;

  return (
    <div>
      <h1 className="text-3xl font-bold">Activity</h1>
      {/* Counts are of the events shown below: the back end keeps the latest 500 since it started. */}
      <p className="mt-2 text-lichen">
        {!connected
          ? "Not connected to the Heimdall back end. Retrying…"
          : events.length === 0
            ? "Nothing yet. Start an agent and ask it to do something."
            : <>Of the {events.length} decisions below, Heimdall allowed <span className="text-allowed">{count("allowed")}</span> and blocked{" "}
                <span className="text-blocked">{count("blocked")}</span>.</>}
      </p>

      {/* Questions that need the user come first */}
      {questions.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-bold">Needs your answer</h2>
          <ul className="mt-4 flex flex-col gap-3">
            {questions.map((q) => (
              <li key={q.request_id}>
                <QuestionCard q={q} />
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

        {/* Ledger: time, what happened, why (with the firewall's rule id), stamp */}
        <ol className="mt-4 border-t border-rule">
          {history.map((e) => (
            <li key={e.id} className="grid grid-cols-[4.5rem_1fr_6.5rem] items-start gap-x-6 border-b border-rule py-4">
              <span className="tabular pt-0.5 text-sm text-lichen">{e.time.slice(0, 5)}</span>
              <div className="min-w-0">
                <p><Sentence e={e} /></p>
                <p className="mt-1 text-sm text-lichen">
                  {e.detail}
                  {e.rule && <span className="ml-2 font-mono text-xs text-lichen/70">rule {e.rule}</span>}
                </p>
              </div>
              <span className={`stamp justify-self-end ${VERDICT_STYLE[e.verdict].text}`}>{VERDICT_STYLE[e.verdict].label}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
