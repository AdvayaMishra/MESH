"use client";
import * as React from "react";
import {
  Background, BackgroundVariant, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, useReactFlow,
  type Edge, type Node, type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AlertTriangle, Cloud, Database, Download, KeyRound, LogIn, MonitorSmartphone, Network, Zap } from "lucide-react";
import { severityStyles } from "@/lib/design-tokens";
import { fmtTime } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";
import type { ChainNode } from "@/lib/types";

const icons = [LogIn, MonitorSmartphone, Zap, KeyRound, Database, Download];

type NodeData = { node: ChainNode; index: number; active: boolean; dim: boolean };

function AttackNode({ data }: NodeProps<Node<NodeData>>) {
  const { node, index, active, dim } = data;
  const s = severityStyles[node.severity];
  const Icon = icons[index] ?? Network;
  return (
    <div
      className={cn(
        "w-[196px] rounded-2xl border-2 bg-white p-3.5 text-left shadow-card transition-all duration-300",
        active ? "scale-[1.04] shadow-pop" : "hover:-translate-y-0.5",
        dim && "opacity-45"
      )}
      style={{ borderColor: active ? s.hex : "#E6EAF5" }}
    >
      <Handle type="target" position={Position.Left} className="!size-2.5 !border-2 !border-white" style={{ background: s.hex }} />
      <div className="flex items-center gap-2.5">
        <span className="relative flex size-9 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: s.hex }}>
          <Icon className="size-[18px]" />
          {node.severity === "critical" && <span className="pulse-ring absolute inset-0 rounded-xl" style={{ color: s.hex }} />}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-ink">{node.label}</p>
          <p className="font-mono text-[11px] text-ink-3">{fmtTime(node.at)} UTC</p>
        </div>
      </div>
      <div className="mt-2.5 flex items-center justify-between">
        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", s.bg, s.text)}>{s.label}</span>
        <span className="text-[11px] font-semibold text-ink-2">+{node.risk} risk</span>
      </div>
      <Handle type="source" position={Position.Right} className="!size-2.5 !border-2 !border-white" style={{ background: s.hex }} />
    </div>
  );
}

const nodeTypes = { attack: AttackNode };
const positions = [
  { x: 0, y: 10 }, { x: 290, y: 60 }, { x: 580, y: 0 },
  { x: 0, y: 220 }, { x: 290, y: 270 }, { x: 580, y: 210 },
];

function Graph({ chain, selectedId, onSelect, replayIndex }: { chain: ChainNode[]; selectedId: string | null; onSelect: (id: string) => void; replayIndex: number | null }) {
  const { fitView } = useReactFlow();
  const nodes: Node<NodeData>[] = chain.map((n, i) => ({
    id: n.id,
    type: "attack",
    position: positions[i % positions.length],
    data: { node: n, index: i, active: selectedId === n.id || replayIndex === i, dim: replayIndex !== null && i > replayIndex },
    draggable: true,
  }));
  const edges: Edge[] = chain.slice(1).map((n, i) => ({
    id: `e${i}`,
    source: chain[i].id,
    target: n.id,
    type: "smoothstep",
    animated: replayIndex === null || i < replayIndex,
    style: { stroke: severityStyles[n.severity].hex, strokeWidth: 3, opacity: replayIndex !== null && i >= replayIndex ? 0.2 : 1 },
    markerEnd: { type: MarkerType.ArrowClosed, color: severityStyles[n.severity].hex, width: 18, height: 18 },
  }));

  React.useEffect(() => {
    const t = setTimeout(() => fitView({ padding: 0.12, duration: 400 }), 60);
    return () => clearTimeout(t);
  }, [fitView, chain.length]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, n) => onSelect(n.id)}
      fitView
      fitViewOptions={{ padding: 0.12 }}
      minZoom={0.4}
      maxZoom={1.4}
      nodesConnectable={false}
      proOptions={{ hideAttribution: true }}
      aria-label="Attack chain graph. Use the list below for a text version."
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.4} color="#d6dcee" />
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
  );
}

export function AttackChainGraph(props: { chain: ChainNode[]; selectedId: string | null; onSelect: (id: string) => void; replayIndex: number | null; height?: number }) {
  return (
    <div className="relative w-full overflow-hidden rounded-2xl bg-gradient-to-br from-[#f7f6ff] via-white to-[#effbff]" style={{ height: props.height ?? 400 }}>
      <ReactFlowProvider>
        <Graph {...props} />
      </ReactFlowProvider>
      <span className="pointer-events-none absolute left-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-medium text-ink-2 shadow-sm"><AlertTriangle className="size-3 text-amber" />Correlated signals, not proof of intent</span>
    </div>
  );
}

export { Cloud };
