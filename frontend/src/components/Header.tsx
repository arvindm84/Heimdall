import heimdallMark from "../assets/heimdall.png";

export type Page = "agents" | "activity" | "flow";

const TABS: { id: Page; label: string }[] = [
  { id: "agents", label: "Agents" },
  { id: "activity", label: "Activity" },
  { id: "flow", label: "Flow" },
];

type Props = {
  page: Page;
  onNavigate: (p: Page) => void;
  waitingCount: number; // requests that need the user's answer
  runningCount: number;
  onStopAll: () => void;
};

export default function Header({ page, onNavigate, waitingCount, runningCount, onStopAll }: Props) {
  return (
    <header className="border-b border-rule">
      {/* Full window width (not the page's centred column): the logo sits at the left edge, like an app. */}
      <div className="flex flex-wrap items-center gap-x-10 gap-y-3 px-8 py-4">
        <span className="flex items-center gap-3">
          {/* Pixel art: head and shoulders, background cut out, saved at 5x its display size so it stays sharp. */}
          <img src={heimdallMark} alt="" className="h-[42px] w-auto" />
          <span className="text-4xl font-bold tracking-tight">Heimdall</span>
        </span>

        <nav className="flex gap-1">
          {TABS.map(({ id, label }) => {
            const active = page === id;
            return (
              <button
                key={id}
                onClick={() => onNavigate(id)}
                aria-current={active ? "page" : undefined}
                className={`relative px-3 py-1.5 transition-colors ${active ? "text-paper" : "text-lichen hover:text-paper"}`}
              >
                {label}
                {/* Waiting requests are the one thing that should pull you to Activity */}
                {id === "activity" && waitingCount > 0 && (
                  <span className="tabular ml-1.5 rounded-full bg-waiting px-1.5 text-xs font-bold text-ground">
                    {waitingCount}
                  </span>
                )}
                {active && <span className="absolute inset-x-3 -bottom-[17px] h-0.5 bg-paper" />}
              </button>
            );
          })}
        </nav>

        <button
          onClick={onStopAll}
          disabled={runningCount === 0}
          className="ml-auto rounded border border-blocked/60 px-3 py-1.5 text-sm text-blocked transition-colors hover:bg-blocked hover:text-ground disabled:border-rule disabled:text-lichen/60 disabled:hover:bg-transparent"
        >
          Stop all agents
        </button>
      </div>
    </header>
  );
}
