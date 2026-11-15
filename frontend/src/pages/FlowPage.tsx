import { useEffect, useMemo, useRef, useState } from "react";
import {
  BaseEdge,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getBezierPath,
  useNodesState,
  useReactFlow,
  useUpdateNodeInternals,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { FolderOpen, Globe, Mail, Sparkles, type LucideIcon } from "lucide-react";
import { VERDICT_STYLE, agentName, type FirewallEvent, type ResourceId, type Verdict } from "../data/events";
import { TOOL_VERB } from "../data/tools";

/*
  Live flow graph, top to bottom:
    agents  ->  Heimdall band  ->  categories (Files, Gmail, Web, AI model)  ->  destinations
  Each new destination an agent touches appears as a new node; the tree re-lays itself out and the
  camera re-frames. Old, unused destinations retire so the graph keeps moving.
*/

// ---------- Timing and sizes ----------

const STEP_MS = 1200; // next queued event (a burst of events plays one by one)
const HOP_MS = 650; // a dot travelling one edge
const MOVE_MS = 600; // nodes sliding to a new layout
const MAX_DESTINATIONS = 8;

const ROW_Y = { agent: 0, gate: 130, category: 300, destination: 450 };
const SLOT = 152; // horizontal space per destination
const W = { agent: 150, category: 140, destination: 136 };
const GATE_H = 84;
const GATE_PAD = 40; // band sticks out past the outermost nodes

const AGENTS = [
  { id: "openclaw", name: "OpenClaw" },
  { id: "hermes", name: "Hermes" },
] as const;

const CATEGORIES: { id: ResourceId; label: string; icon: LucideIcon }[] = [
  { id: "files", label: "Files", icon: FolderOpen },
  { id: "gmail", label: "Gmail", icon: Mail },
  { id: "web", label: "Web", icon: Globe },
  { id: "model", label: "AI model", icon: Sparkles },
];

// ---------- Destinations ----------

// Only events with a resource are drawn (see data/events.ts).
type Drawn = FirewallEvent & { resource: ResourceId };

type Destination = { key: string; label: string; full: string; category: ResourceId; verdict: Verdict; lastUsed: number; order: number };

// Where a request was going, as a short label: a host, a file path, or an inbox.
function destinationOf(e: Drawn): { key: string; label: string; full: string } {
  let label = e.target;
  if (e.resource === "web") {
    try {
      label = new URL(e.target).host;
    } catch {
      /* keep the raw target */
    }
  }
  if (e.action === "gmail_read") label = "Inbox";
  // Files: just the name ("contacts.md", "notes/"), so two paths in one folder don't truncate to the same text.
  if (e.resource === "files") label = (e.target.split("/").pop() ?? e.target) + (e.action === "files_list" ? "/" : "");
  // Same host or inbox = same node; files are told apart by full path.
  return { key: `${e.resource}:${e.resource === "files" ? e.target : label}`, label, full: e.target };
}

// ---------- Layout ----------

type XY = { x: number; y: number };

function layout(destinations: Destination[]) {
  const positions: Record<string, XY> = {};
  const categoryX: Record<string, number> = {};
  let cursor = 0;

  // Destinations sit side by side, grouped under their category. Empty categories still get one slot.
  for (const cat of CATEGORIES) {
    const mine = destinations.filter((d) => d.category === cat.id).sort((a, b) => a.order - b.order);
    const slots = Math.max(1, mine.length);
    mine.forEach((d, i) => {
      positions[d.key] = { x: cursor + i * SLOT + SLOT / 2 - W.destination / 2, y: ROW_Y.destination };
    });
    categoryX[cat.id] = cursor + (slots * SLOT) / 2;
    positions[cat.id] = { x: categoryX[cat.id] - W.category / 2, y: ROW_Y.category };
    cursor += slots * SLOT;
  }

  const width = cursor;
  const agentX: Record<string, number> = {};
  AGENTS.forEach((a, i) => {
    agentX[a.id] = (width * (i + 1)) / (AGENTS.length + 1);
    positions[a.id] = { x: agentX[a.id] - W.agent / 2, y: ROW_Y.agent };
  });
  positions.gate = { x: -GATE_PAD, y: ROW_Y.gate };

  // Where edges meet the band, as % of the band's width.
  const gateWidth = width + GATE_PAD * 2;
  const pct = (x: number) => ((x + GATE_PAD) / gateWidth) * 100;
  return {
    positions,
    gateWidth,
    ins: AGENTS.map((a) => ({ id: a.id, pct: pct(agentX[a.id]) })),
    outs: CATEGORIES.map((c) => ({ id: c.id, pct: pct(categoryX[c.id]) })),
  };
}

// Slide nodes from their old spots to new ones (edges follow because positions update every frame).
function useTween(target: Record<string, XY>) {
  const [current, setCurrent] = useState(target);
  const currentRef = useRef(target);
  const key = JSON.stringify(target);

  useEffect(() => {
    const from = currentRef.current;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      // Clamp at 0 too: the frame timestamp can be slightly earlier than `start`.
      const t = Math.min(1, Math.max(0, (now - start) / MOVE_MS));
      const ease = 1 - Math.pow(1 - t, 3);
      const next: Record<string, XY> = {};
      for (const [id, to] of Object.entries(target)) {
        const f = from[id] ?? to; // brand-new nodes start in place (they pop in instead)
        next[id] = { x: f.x + (to.x - f.x) * ease, y: f.y + (to.y - f.y) * ease };
      }
      currentRef.current = next;
      setCurrent(next);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return current;
}

// ---------- Nodes ----------

const hidden = { opacity: 0 }; // handles exist for edges but aren't shown

type AgentData = { name: string; active: boolean };
type GateData = {
  width: number;
  ins: { id: string; pct: number }[];
  outs: { id: string; pct: number }[];
  current: Drawn | null;
  stampAt: number; // % across the band where the latest request crossed
  counts: Counts;
};
// Allowed / blocked of every event received, plus questions waiting on the user.
type Counts = { allowed: number; blocked: number; waiting: number };
type CategoryData = { label: string; icon: LucideIcon; active: boolean };
type DestinationData = { label: string; full: string; verdict: Verdict; active: boolean };

function AgentNode({ data }: NodeProps<Node<AgentData>>) {
  return (
    <div
      className={`rounded-md border bg-raised px-4 py-3 text-center transition-colors ${data.active ? "border-paper" : "border-rule"}`}
      style={{ width: W.agent }}
    >
      <div className="font-bold">{data.name}</div>
      <div className="text-xs text-lichen">Agent</div>
      <Handle type="source" position={Position.Bottom} style={hidden} />
    </div>
  );
}

// The checkpoint: a band every request crosses. The verdict stamp lands where the request hit it.
function GateNode({ id, data }: NodeProps<Node<GateData>>) {
  const updateInternals = useUpdateNodeInternals();
  const handleKey = JSON.stringify([data.ins, data.outs]);
  useEffect(() => updateInternals(id), [id, handleKey, updateInternals]);

  const ink = data.current ? VERDICT_STYLE[data.current.verdict] : null;
  return (
    <div
      className="relative rounded-md border-2 bg-raised transition-colors duration-300"
      style={{ width: data.width, height: GATE_H, borderColor: ink?.hex ?? "var(--color-rule)" }}
    >
      {data.ins.map((h) => (
        <Handle key={h.id} id={`in-${h.id}`} type="target" position={Position.Top} style={{ ...hidden, left: `${h.pct}%` }} />
      ))}
      {data.outs.map((h) => (
        <Handle key={h.id} id={`out-${h.id}`} type="source" position={Position.Bottom} style={{ ...hidden, left: `${h.pct}%` }} />
      ))}

      <div className="flex h-full items-center justify-between px-5">
        <div>
          <div className="text-xl font-bold">Heimdall</div>
          <div className="text-xs text-lichen">Every request crosses here</div>
        </div>
        <div className="tabular flex gap-4 text-sm">
          <span className="text-allowed">{data.counts.allowed} allowed</span>
          <span className="text-blocked">{data.counts.blocked} blocked</span>
          <span className="text-waiting">{data.counts.waiting} waiting</span>
        </div>
      </div>

      {data.current && ink && (
        <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: `${data.stampAt}%` }}>
          <span key={data.current.id} className={`stamp stamp-land block bg-raised ${ink.text}`}>
            {ink.label}
          </span>
        </div>
      )}
    </div>
  );
}

function CategoryNode({ data }: NodeProps<Node<CategoryData>>) {
  const Icon = data.icon;
  return (
    <div
      className={`flex items-center justify-center gap-2 rounded-md border bg-raised px-3 py-2.5 transition-colors ${data.active ? "border-allowed" : "border-rule"}`}
      style={{ width: W.category }}
    >
      <Handle type="target" position={Position.Top} style={hidden} />
      <Icon className={`size-4 ${data.active ? "text-allowed" : "text-lichen"}`} strokeWidth={1.75} />
      <span className="font-bold">{data.label}</span>
      <Handle type="source" position={Position.Bottom} style={hidden} />
    </div>
  );
}

// A place an agent tried to reach. Blocked ones are struck through: the request never got there.
function DestinationNode({ data }: NodeProps<Node<DestinationData>>) {
  const style = {
    allowed: "border-rule",
    blocked: "border-dashed border-blocked/70 text-blocked line-through decoration-blocked/70",
    flagged: "border-dashed border-waiting/70 text-waiting",
  }[data.verdict];
  return (
    <div className="node-enter" style={{ width: W.destination }}>
      <Handle type="target" position={Position.Top} style={hidden} />
      <div
        className={`truncate rounded-md border bg-raised px-3 py-2 text-center font-mono text-xs transition-colors ${style} ${
          data.active && data.verdict === "allowed" ? "border-allowed" : ""
        }`}
        title={data.full}
      >
        {data.label}
      </div>
    </div>
  );
}

const nodeTypes = { agent: AgentNode, gate: GateNode, category: CategoryNode, destination: DestinationNode };

// ---------- Edges ----------

type EdgeData = { color: string | null; pulse: number; delay: number; dashed?: string };

// Moves a dot along the edge with requestAnimationFrame (same in Chrome and the Mac desktop window).
function Pulse({ path, color, delay }: { path: string; color: string; delay: number }) {
  const pathRef = useRef<SVGPathElement>(null);
  const dotRef = useRef<SVGCircleElement>(null);

  useEffect(() => {
    const p = pathRef.current!;
    const dot = dotRef.current!;
    const start = performance.now() + delay;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, Math.max(0, (now - start) / HOP_MS));
      const point = p.getPointAtLength(p.getTotalLength() * t);
      dot.setAttribute("cx", String(point.x));
      dot.setAttribute("cy", String(point.y));
      dot.style.opacity = now < start || t >= 1 ? "0" : "1";
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [path, delay]);

  return (
    <g>
      <path ref={pathRef} d={path} fill="none" stroke="none" />
      <circle ref={dotRef} r={4.5} fill={color} opacity={0} />
    </g>
  );
}

function FlowEdge(props: EdgeProps<Edge<EdgeData>>) {
  const [path] = getBezierPath(props);
  const d = props.data!;
  return (
    <>
      <BaseEdge
        id={props.id}
        path={path}
        style={{
          stroke: d.color ?? d.dashed ?? "var(--color-rule)",
          strokeWidth: d.color ? 2 : 1.25,
          strokeDasharray: d.dashed && !d.color ? "4 4" : undefined,
          opacity: d.dashed && !d.color ? 0.6 : 1,
          transition: "stroke 300ms",
        }}
      />
      {d.color && <Pulse key={d.pulse} path={path} color={d.color} delay={d.delay} />}
    </>
  );
}

const edgeTypes = { flow: FlowEdge };

// ---------- Graph ----------

function FlowGraph({ events, counts, onPlayed }: { events: FirewallEvent[]; counts: Counts; onPlayed: (e: Drawn) => void }) {
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [current, setCurrent] = useState<Drawn | null>(null);
  // In refs so React's dev-mode double mount doesn't replay events.
  const queue = useRef<Drawn[]>([]);
  const lastQueued = useRef(-1); // id of the newest event put in the queue
  const step = useRef(0); // plays so far: orders destinations and finds the stalest

  // New events join the queue. On first open, only the latest few, so the page doesn't replay the whole history.
  useEffect(() => {
    const drawn = events.filter((e): e is Drawn => e.resource !== null);
    // A smaller newest id means the back end restarted (ids start again at 1).
    if (drawn.length && drawn[drawn.length - 1].id < lastQueued.current) lastQueued.current = -1;
    const fresh = drawn.filter((e) => e.id > lastQueued.current);
    if (!fresh.length) return;
    queue.current.push(...(lastQueued.current < 0 ? fresh.slice(-MAX_DESTINATIONS) : fresh));
    lastQueued.current = fresh[fresh.length - 1].id;
  }, [events]);

  // Play the next queued event, adding its destination if it's new and retiring the stalest one.
  useEffect(() => {
    const play = () => {
      const event = queue.current.shift();
      if (!event) return;
      const n = step.current++;
      const { key, label, full } = destinationOf(event);

      setDestinations((prev) => {
        const existing = prev.find((d) => d.key === key);
        let next = existing
          ? prev.map((d) => (d.key === key ? { ...d, verdict: event.verdict, lastUsed: n } : d))
          : [...prev, { key, label, full, category: event.resource, verdict: event.verdict, lastUsed: n, order: n }];
        if (next.length > MAX_DESTINATIONS) {
          const stalest = next.reduce((a, b) => (a.lastUsed <= b.lastUsed ? a : b));
          next = next.filter((d) => d !== stalest);
        }
        return next;
      });
      setCurrent(event);
      onPlayed(event);
    };
    play();
    const timer = setInterval(play, STEP_MS);
    return () => clearInterval(timer);
  }, [onPlayed]);

  const plan = useMemo(() => layout(destinations), [destinations]);
  const positions = useTween(plan.positions);
  const currentKey = current ? destinationOf(current).key : null;
  const stampAt = current ? plan.ins.find((h) => h.id === current.agent)?.pct ?? 50 : 50;

  // Build nodes from the (animated) positions.
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  useEffect(() => {
    const at = (id: string) => positions[id] ?? plan.positions[id];
    const built: Node[] = [
      ...AGENTS.map((a) => ({
        id: a.id,
        type: "agent",
        position: at(a.id),
        data: { name: a.name, active: current?.agent === a.id },
      })),
      {
        id: "gate",
        type: "gate",
        position: at("gate"),
        data: { width: plan.gateWidth, ins: plan.ins, outs: plan.outs, current, stampAt, counts },
      },
      ...CATEGORIES.map((c) => ({
        id: c.id,
        type: "category",
        position: at(c.id),
        data: { label: c.label, icon: c.icon, active: current?.verdict === "allowed" && current.resource === c.id },
      })),
      ...destinations.map((d) => ({
        id: d.key,
        type: "destination",
        position: at(d.key),
        data: { label: d.label, full: d.full, verdict: d.verdict, active: d.key === currentKey },
      })),
    ];
    // Keep React Flow's measured sizes from the previous render.
    setNodes((prev) => {
      const byId = new Map(prev.map((n) => [n.id, n]));
      return built.map((n) => ({ ...byId.get(n.id), ...n }));
    });
  }, [positions, plan, destinations, current, currentKey, stampAt, counts, setNodes]);

  // Edges: agent -> band -> category -> destination. Only the current request's path lights up.
  const edges: Edge<EdgeData>[] = useMemo(() => {
    const color = current ? VERDICT_STYLE[current.verdict].hex : null;
    const allowed = current?.verdict === "allowed";
    const pulse = current?.id ?? 0;
    return [
      ...AGENTS.map((a) => ({
        id: `${a.id}-gate`,
        source: a.id,
        target: "gate",
        targetHandle: `in-${a.id}`,
        type: "flow",
        data: { color: current?.agent === a.id ? color : null, pulse, delay: 0 },
      })),
      ...CATEGORIES.map((c) => ({
        id: `gate-${c.id}`,
        source: "gate",
        sourceHandle: `out-${c.id}`,
        target: c.id,
        type: "flow",
        data: { color: allowed && current?.resource === c.id ? color : null, pulse, delay: HOP_MS },
      })),
      ...destinations.map((d) => ({
        id: `${d.category}-${d.key}`,
        source: d.category,
        target: d.key,
        type: "flow",
        data: {
          color: allowed && d.key === currentKey ? color : null,
          pulse,
          delay: HOP_MS * 2,
          // Blocked or waiting destinations hang off a dashed line: nothing got through.
          dashed: d.verdict === "allowed" ? undefined : VERDICT_STYLE[d.verdict].hex,
        },
      })),
    ];
  }, [current, currentKey, destinations]);

  // Re-frame the camera once nodes have slid into a new layout.
  const { fitView } = useReactFlow();
  useEffect(() => {
    const t = setTimeout(() => fitView({ duration: 500, padding: 0.08 }), MOVE_MS + 50);
    return () => clearTimeout(t);
  }, [plan.gateWidth, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      colorMode="dark"
      fitView
      fitViewOptions={{ padding: 0.08 }}
      nodesDraggable={false}
      nodesConnectable={false}
      zoomOnScroll={false}
      preventScrolling={false}
      proOptions={{ hideAttribution: true }}
      style={{ background: "transparent" }}
    />
  );
}

// ---------- Page ----------

type Props = { events: FirewallEvent[]; waitingCount: number };

export default function FlowPage({ events, waitingCount }: Props) {
  const [played, setPlayed] = useState<Drawn[]>([]); // newest first
  const onPlayed = useMemo(() => (e: Drawn) => setPlayed((prev) => [e, ...prev].slice(0, 4)), []);
  // Counted over every event received, not just the ones drawn, so the band never undercounts.
  const counts: Counts = useMemo(
    () => ({
      allowed: events.filter((e) => e.verdict === "allowed").length,
      blocked: events.filter((e) => e.verdict === "blocked").length,
      waiting: waitingCount,
    }),
    [events, waitingCount],
  );

  return (
    <div>
      <h1 className="text-3xl font-bold">Flow</h1>
      <p className="mt-2 max-w-[62ch] text-lichen">
        Every request an agent makes crosses Heimdall. New places your agents reach appear as they happen; blocked ones
        are struck through because nothing got there.
        {events.length === 0 && " Nothing yet: start an agent and ask it to do something."}
      </p>

      <div className="mt-8 h-[560px] overflow-hidden rounded-md border border-rule">
        <ReactFlowProvider>
          <FlowGraph events={events} counts={counts} onPlayed={onPlayed} />
        </ReactFlowProvider>
      </div>

      {/* The last few requests, in sentences */}
      <ol className="mt-6 grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        {played.map((e) => (
          <li key={e.id} className="border-t border-rule pt-3 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <span className={`font-bold ${VERDICT_STYLE[e.verdict].text}`}>{VERDICT_STYLE[e.verdict].label}</span>
              <span className="tabular text-xs text-lichen">{e.time}</span>
            </div>
            <p className="mt-1 text-lichen">
              {agentName(e.agent)} wanted to {TOOL_VERB[e.action] ?? e.action}
            </p>
            <p className="truncate font-mono text-xs" title={e.target}>
              {e.target}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}
