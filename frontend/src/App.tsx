import { useState } from "react";
import Header, { type Page } from "./components/Header";
import AgentsPage from "./pages/AgentsPage";
import FlowPage from "./pages/FlowPage";
import ActivityPage from "./pages/ActivityPage";
import { MOCK_AGENTS, type Agent } from "./data/agents";
import { SAMPLE_EVENTS } from "./data/sample";

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

  const [agents, setAgents] = useState<Agent[]>(MOCK_AGENTS);
  const setStatus = (id: string, status: Agent["status"]) =>
    setAgents((all) => all.map((a) => (a.id === id ? { ...a, status } : a)));

  // MOCK start/stop: will call POST /api/launch and /api/kill once those routes are ready.
  const start = (id: string) => {
    setStatus(id, "sealing");
    setTimeout(() => setStatus(id, "running"), 2200);
  };
  const stop = (id: string) => setStatus(id, "stopped");
  const stopAll = () => setAgents((all) => all.map((a) => ({ ...a, status: "stopped" })));

  const running = agents.filter((a) => a.status === "running").length;
  const waiting = SAMPLE_EVENTS.filter((e) => e.verdict === "waiting").length; // SAMPLE

  return (
    <div className="flex h-full flex-col">
      <Header page={page} onNavigate={setPage} waitingCount={waiting} runningCount={running} onStopAll={stopAll} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-10">
          {page === "agents" && <AgentsPage agents={agents} onStart={start} onStop={stop} />}
          {page === "activity" && <ActivityPage />}
          {page === "flow" && <FlowPage />}
        </div>
      </main>
    </div>
  );
}
