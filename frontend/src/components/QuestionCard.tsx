import { useState } from "react";
import { agentName } from "../data/events";
import { TOOL_VERB } from "../data/tools";
import { ApiError, api } from "../lib/api";
import type { Question } from "../lib/live";

// One firewall question with Approve / Deny. Used by the pop-up and the Activity page.
// The card disappears when the back end sends `event: resolved`, not when the button is clicked,
// so the pop-up and the Activity page always agree.
export default function QuestionCard({ q }: { q: Question }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answer = async (decision: "approve" | "deny") => {
    setBusy(true);
    setError(null);
    try {
      await api.respond(q.request_id, decision);
    } catch (e) {
      // 404: the agent stopped waiting (2 minutes passed), which counted as a deny.
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const consent = q.kind === "consent";
  return (
    <div className="rounded-md border border-waiting/50 bg-raised px-5 py-4 shadow-lg">
      <p className="text-xs font-bold uppercase tracking-wide text-waiting">
        {consent ? "Confidential data" : "Needs your approval"} · {agentName(q.container_id)}
      </p>
      <p className="mt-2">{q.question}</p>

      {/* What exactly is about to happen, from the firewall's fields */}
      {q.tool === "gmail_send" ? (
        // The final email with real values: exactly what will be sent. Shown only, never stored.
        <dl className="mt-3 grid grid-cols-[5rem_1fr] gap-x-3 gap-y-1 rounded border border-rule px-3 py-2 text-sm">
          <dt className="text-lichen">To</dt>
          <dd className="break-all font-mono">{q.to}</dd>
          <dt className="text-lichen">Subject</dt>
          <dd>{q.subject}</dd>
          <dt className="text-lichen">Message</dt>
          <dd className="max-h-48 overflow-y-auto whitespace-pre-wrap">{q.body}</dd>
        </dl>
      ) : q.tool && q.path ? (
        <p className="mt-2 text-sm text-lichen">
          Wants to {TOOL_VERB[q.tool] ?? q.tool} <span className="break-all font-mono text-paper">{q.path}</span>
        </p>
      ) : q.file ? (
        <p className="mt-2 text-sm text-lichen">
          File <span className="font-mono text-paper">{q.file}</span> → {q.provider}
        </p>
      ) : null}

      {error && <p className="mt-2 text-sm text-blocked">{error}</p>}

      <div className="mt-4 flex justify-end gap-2">
        <button
          disabled={busy}
          onClick={() => answer("deny")}
          className="rounded border border-rule px-4 py-2 text-sm transition-colors hover:border-blocked hover:text-blocked disabled:opacity-50"
        >
          Deny
        </button>
        <button
          disabled={busy}
          onClick={() => answer("approve")}
          className="rounded bg-paper px-4 py-2 text-sm font-bold text-ground hover:opacity-90 disabled:opacity-50"
        >
          {/* An approve lasts for this agent's run (the gateway remembers consent per file). */}
          {consent ? "Allow for this session" : q.tool === "gmail_send" ? "Send it" : "Allow"}
        </button>
      </div>
    </div>
  );
}
