import { useEffect, useState } from "react";
import Header, { type Page } from "./components/Header";
import AgentsPage from "./pages/AgentsPage";
import FlowPage from "./pages/FlowPage";
import ActivityPage from "./pages/ActivityPage";
import { AGENT_PROFILES, type Agent } from "./data/agents";
import { SAMPLE_EVENTS } from "./data/sample";
import { ApiError, api } from "./lib/api";

// Turn any thrown error into what an agent row shows.
const toError = (e: unknown) =>
  e instanceof ApiError ? { message: e.message, detail: e.detail } : { message: String(e) };

export default function App() {
  // Page lives in the URL hash (#flow, #activity) so a refresh keeps you where you were.
  const [page, setPageState] = useState<Page>(() => {
    const hash = window.location.hash.slice(1);
    return hash === "flow" || hash === "activity" ? hash : "agents";
  });
  const setPage = (p: Page) => {
    window.location.hash = p;
    setPageState(p);
  };

  const [agents, setAgents] = useState<Agent[]>(() =>
    AGENT_PROFILES.map((p) => ({ ...p, status: "stopped", chat: null, error: null })),
  );
  const [backendError, setBackendError] = useState<string | null>(null);

  const update = (id: string, changes: Partial<Agent>) =>
    setAgents((all) => all.map((a) => (a.id === id ? { ...a, ...changes } : a)));

  // On load (and after a reload): ask the back end which agents are already running.
  useEffect(() => {
    api
      .agents()
      .then(({ agents: live }) =>
        setAgents((all) =>
          all.map((a) => {
            const chat = live.find((l) => l.name === a.id)?.chat ?? null;
            return { ...a, chat, status: chat ? "running" : "stopped" };
          }),
        ),
      )
      .catch((e) => setBackendError(toError(e).message));
  }, []);

  // Start: builds and starts the container, then returns the chat login. Can take minutes.
  const start = async (id: string) => {
    const agent = agents.find((a) => a.id === id)!;
    update(id, { status: "starting", error: null });
    try {
      const chat = await api.launch(id, agent.config);
      update(id, { status: "running", chat });
    } catch (e) {
      update(id, { status: "stopped", error: toError(e) });
    }
  };

  // Stop: stops the container but keeps it, so Start is quicker next time.
  const stop = async (id: string) => {
    update(id, { status: "stopping", error: null });
    try {
      await api.stop(id);
      update(id, { status: "stopped", chat: null });
    } catch (e) {
      update(id, { status: "running", error: toError(e) });
    }
  };

  // Kill switch: kill and remove every running agent's container, one at a time.
  const stopAll = async () => {
    for (const a of agents.filter((a) => a.status === "running")) {
      update(a.id, { status: "stopping", error: null });
      try {
        await api.kill(a.id);
        update(a.id, { status: "stopped", chat: null });
      } catch (e) {
        update(a.id, { status: "running", error: toError(e) });
      }
    }
  };

  const running = agents.filter((a) => a.status === "running").length;
  const waiting = SAMPLE_EVENTS.filter((e) => e.verdict === "waiting").length; // SAMPLE

  return (
    <div className="flex h-full flex-col">
      <Header page={page} onNavigate={setPage} waitingCount={waiting} runningCount={running} onStopAll={stopAll} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-10">
          {page === "agents" && <AgentsPage agents={agents} backendError={backendError} onStart={start} onStop={stop} />}
          {page === "activity" && <ActivityPage />}
          {page === "flow" && <FlowPage />}
        </div>
      </main>
    </div>
  );
}
