import dagre from "@dagrejs/dagre";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import clsx from "clsx";
import {
  AtSign,
  Building2,
  FileText,
  GitBranch,
  Globe,
  Image,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Server,
  ShieldCheck,
  User,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { memo, useMemo, useState } from "react";
import { useEvidence } from "../../context/evidence";
import { CONFIDENCE_META, ENTITY_KIND_LABEL, PLATFORM_META } from "../../lib/meta";
import { useResolvedTheme } from "../../lib/theme";
import type { Graph, GraphNode } from "../../lib/types";
import { ConfidenceBadge } from "../ui/indicators";
import { Button, ExternalLink } from "../ui/primitives";

const KIND_ICON: Record<string, LucideIcon> = {
  person: User,
  username: AtSign,
  email: Mail,
  phone: Phone,
  profile: UserRound,
  organization: Building2,
  website: Globe,
  domain: Globe,
  repository: GitBranch,
  document: FileText,
  ip: Server,
  certificate: ShieldCheck,
  mention: MessageSquare,
  location: MapPin,
  image: Image,
};

const NODE_W = 200;
const NODE_H = 46;

type EntityNodeData = { node: GraphNode; selected: boolean };

const EntityNode = memo(function EntityNode({ data }: NodeProps<Node<EntityNodeData>>) {
  const n = data.node;
  const Icon = KIND_ICON[n.kind] ?? Globe;
  const central = n.is_subject || n.is_seed;
  const color = CONFIDENCE_META[n.level].color;
  const platform = n.data.platform ? PLATFORM_META[n.data.platform]?.label ?? n.data.platform : null;
  return (
    <div
      className={clsx(
        "flex items-center gap-2 rounded-lg border bg-surface px-2.5 shadow-sm transition-colors",
        data.selected ? "border-accent" : central ? "border-line-strong" : "border-line",
        central && "bg-surface-3",
      )}
      style={{ width: NODE_W, height: NODE_H }}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-line-strong" />
      <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-surface-2 text-muted">
        <Icon className="size-3.5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className={clsx("truncate text-[12px] text-fg", central && "font-semibold")}>{n.label}</div>
        <div className="truncate text-[10px] text-subtle uppercase tracking-wide">
          {platform ? `${platform} ${ENTITY_KIND_LABEL[n.kind] ?? n.kind}` : (ENTITY_KIND_LABEL[n.kind] ?? n.kind)}
        </div>
      </div>
      <span className="size-1.5 shrink-0 rounded-full" style={{ background: color }} title={`${n.level} confidence`} />
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-line-strong" />
    </div>
  );
});

const nodeTypes = { entity: EntityNode };

/** Positions depend only on the graph and the kind filter, never on selection. */
function layout(graph: Graph, hidden: Set<string>) {
  const visible = graph.nodes.filter((n) => !hidden.has(n.kind) || n.is_subject || n.is_seed);
  const ids = new Set(visible.map((n) => n.id));
  const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 14, ranksep: 90, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  visible.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  const positions = new Map(visible.map((n) => {
    const p = g.node(n.id);
    return [n.id, { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 }];
  }));
  return { visible, edges, positions };
}

function styleGraph(base: ReturnType<typeof layout>, selectedId: string | null) {
  const nodes: Node<EntityNodeData>[] = base.visible.map((n) => ({
    id: n.id,
    type: "entity",
    position: base.positions.get(n.id)!,
    data: { node: n, selected: n.id === selectedId },
  }));
  const edges: Edge[] = base.edges.map((e) => {
    const touchesSelection = selectedId !== null && (e.source === selectedId || e.target === selectedId);
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: touchesSelection ? e.type : undefined,
      labelStyle: { fill: "var(--text-muted)", fontSize: 10, fontFamily: "var(--font-mono)" },
      labelBgStyle: { fill: "var(--surface)" },
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: "var(--border-strong)" },
      style: {
        stroke: touchesSelection ? "var(--accent)" : e.inferred ? "var(--conf-medium)" : "var(--border-strong)",
        strokeDasharray: e.inferred ? "4 4" : undefined,
        strokeWidth: touchesSelection ? 1.6 : 1,
        opacity: 0.35 + 0.65 * e.confidence,
      },
    };
  });
  return { nodes, edges };
}

function NodeInspector({ graph, node, onClose }: { graph: Graph; node: GraphNode; onClose: () => void }) {
  const { open } = useEvidence();
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const related = graph.edges
    .filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => ({ edge: e, other: byId.get(e.source === node.id ? e.target : e.source) }))
    .filter((r) => r.other);
  const isMention = node.kind === "mention";
  const platform = node.data.platform ? PLATFORM_META[node.data.platform]?.label ?? node.data.platform : null;
  return (
    <aside
      aria-label="Node inspector"
      className="absolute top-3 right-3 bottom-3 z-10 flex w-72 flex-col rounded-lg border border-line-strong bg-surface shadow-2xl"
    >
      <header className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <div className="label-caps">
            {platform ? `${platform} ` : ""}
            {ENTITY_KIND_LABEL[node.kind] ?? node.kind}
          </div>
          <div className="mt-0.5 truncate text-sm font-semibold text-fg">{node.label}</div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close inspector" className="rounded p-0.5 text-muted hover:text-fg">
          <X className="size-4" />
        </button>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3 text-[13px]">
        <div className="space-y-1">
          <ConfidenceBadge score={node.confidence} level={node.level} />
          {node.data.match_label && <div className="text-xs text-muted">{node.data.match_label}</div>}
        </div>
        {related.length > 0 && (
          <div>
            <div className="label-caps mb-1.5">Related entities</div>
            <ul className="space-y-1">
              {related.slice(0, 25).map(({ edge, other }) => (
                <li key={edge.id} className="flex items-center gap-2 text-xs">
                  <span className="w-24 shrink-0 font-mono text-[10px] text-subtle">{edge.type}</span>
                  <span className="truncate text-fg">
                    {other!.data.platform ? `${PLATFORM_META[other!.data.platform]?.label ?? other!.data.platform} ` : ""}
                    {other!.label}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <footer className="flex gap-2 border-t border-line px-4 py-3">
        {node.data.url && (
          <ExternalLink
            href={String(node.data.url)}
            className="inline-flex h-7 items-center rounded-md border border-line-strong bg-surface-2 px-2.5 text-xs font-medium text-fg hover:bg-surface-3"
          >
            Open source
          </ExternalLink>
        )}
        {!isMention && (
          <Button size="sm" variant="ghost" onClick={() => open({ type: "entity", id: node.id })}>
            View evidence
          </Button>
        )}
      </footer>
    </aside>
  );
}

export function GraphView({ graph }: { graph: Graph }) {
  const theme = useResolvedTheme();
  const [selected, setSelected] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(["certificate"]));
  const kinds = useMemo(() => {
    const counts = new Map<string, number>();
    graph.nodes.forEach((n) => counts.set(n.kind, (counts.get(n.kind) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [graph]);
  const base = useMemo(() => layout(graph, hidden), [graph, hidden]);
  const { nodes, edges } = useMemo(() => styleGraph(base, selected), [base, selected]);
  const selectedNode = graph.nodes.find((n) => n.id === selected) ?? null;

  const toggle = (kind: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-4 py-2">
        <span className="mr-1 text-xs text-subtle">Show:</span>
        {kinds.map(([kind, count]) => (
          <button
            key={kind}
            type="button"
            aria-pressed={!hidden.has(kind)}
            onClick={() => toggle(kind)}
            className={clsx(
              "rounded border px-2 py-0.5 text-[11px]",
              hidden.has(kind) ? "border-line text-subtle line-through" : "border-line-strong text-muted hover:text-fg",
            )}
          >
            {ENTITY_KIND_LABEL[kind] ?? kind} <span className="text-subtle">{count}</span>
          </button>
        ))}
        <span className="ml-auto flex items-center gap-3 text-[11px] text-subtle">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-5 border-t border-line-strong" /> sourced
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-5 border-t border-dashed" style={{ borderColor: "var(--conf-medium)" }} /> inferred
          </span>
        </span>
      </div>
      <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, n) => setSelected(n.id)}
          onPaneClick={() => setSelected(null)}
          nodesConnectable={false}
          nodesDraggable={false}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.15}
          proOptions={{ hideAttribution: true }}
          colorMode={theme}
        >
          <Background gap={24} size={1} color="var(--border)" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor={() => "var(--border-strong)"} maskColor="color-mix(in srgb, var(--bg) 70%, transparent)" />
        </ReactFlow>
        {selectedNode && <NodeInspector graph={graph} node={selectedNode} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}
