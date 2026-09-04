"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ENTITY_LABELS, patternLabel, riskColor } from "@/lib/labels";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

export type RingNode = {
  id: string;
  type: string;
  label: string;
  short_label: string;
  risk: number;
  txn_count: number;
  user_count: number;
  total_inr: number;
  patterns: string[];
  cluster_id: string;
  is_hub?: boolean;
};

export type RingLink = {
  source: string;
  target: string;
  transaction_id?: string;
  amount_inr?: number;
  risk_score?: number;
  relation?: string;
  cluster_id?: string;
};

export type RingCluster = {
  id: string;
  hub_id: string;
  hub_label: string;
  txn_count: number;
  volume_inr: number;
  max_risk: number;
  pattern?: string | null;
  members: Record<string, number>;
};

const TYPE_COLORS: Record<string, string> = {
  device: "#ef4444",
  ip: "#f97316",
  address: "#eab308",
  user: "#22c55e",
};

const CLUSTER_PALETTE = ["#f87171", "#fb923c", "#fbbf24", "#a78bfa", "#38bdf8", "#34d399"];

const RELATION_LABELS: Record<string, string> = {
  "same-txn-ip": "Device ↔ IP (same txn)",
  "same-txn-address": "Device ↔ Address (same txn)",
  "same-txn-user": "Device ↔ User (same txn)",
};

function clusterColor(clusterId: string): string {
  const idx = parseInt(clusterId.replace("ring_", ""), 10);
  return CLUSTER_PALETTE[isNaN(idx) ? 0 : idx % CLUSTER_PALETTE.length];
}

export default function RingGraph({
  nodes,
  links,
  clusters,
  selectedId,
  onNodeClick,
}: {
  nodes: RingNode[];
  links: RingLink[];
  clusters: RingCluster[];
  selectedId?: string | null;
  onNodeClick?: (node: RingNode) => void;
}) {
  const ref = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 900, h: 480 });
  const [hover, setHover] = useState<RingNode | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setSize({ w: el.clientWidth || 900, h: el.clientHeight || 480 });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const graphData = useMemo(() => {
    const nodeMap = new Map(nodes.map((n) => [n.id, { ...n }]));
    const validLinks = links
      .map((l) => ({
        ...l,
        source: typeof l.source === "string" ? l.source : (l as any).source?.id,
        target: typeof l.target === "string" ? l.target : (l as any).target?.id,
      }))
      .filter((l) => l.source && l.target && nodeMap.has(l.source) && nodeMap.has(l.target));

    return { nodes: Array.from(nodeMap.values()), links: validLinks };
  }, [nodes, links]);

  useEffect(() => {
    if (!ref.current || !graphData.nodes.length) return;
    ref.current.d3Force("charge")?.strength(-320);
    ref.current.d3Force("link")?.distance((link: any) => (link.source?.is_hub || link.target?.is_hub ? 90 : 55));
    ref.current.d3Force("center")?.strength(0.04);
    const timer = setTimeout(() => ref.current?.zoomToFit(600, 100), 500);
    return () => clearTimeout(timer);
  }, [graphData.nodes.length, graphData.links.length, size.w, clusters.length]);

  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as RingNode & { x: number; y: number };
      const r = (n.is_hub ? 10 : 7) + Math.min(n.txn_count, 8) * 0.4;
      const fill = TYPE_COLORS[n.type] || "#94a3b8";
      const ring = clusterColor(n.cluster_id);
      const isSelected = selectedId === n.id;
      const isHover = hover?.id === n.id;

      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.lineWidth = isSelected || isHover ? 3 / globalScale : 2 / globalScale;
      ctx.strokeStyle = isSelected ? "#fff" : ring;
      ctx.stroke();

      if (n.is_hub) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 4 / globalScale, 0, 2 * Math.PI);
        ctx.strokeStyle = ring;
        ctx.lineWidth = 1.5 / globalScale;
        ctx.setLineDash([3 / globalScale, 2 / globalScale]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      const fontSize = Math.max(10 / globalScale, 3);
      ctx.font = `${n.is_hub ? "bold " : ""}${fontSize}px ui-monospace, monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = "rgba(255,255,255,0.92)";
      ctx.fillText(n.short_label || n.label, n.x, n.y + r + 2 / globalScale);

      if (globalScale > 0.55) {
        ctx.font = `${fontSize * 0.85}px ui-monospace, monospace`;
        ctx.fillStyle = "rgba(148,163,184,0.95)";
        ctx.fillText(`risk ${n.risk.toFixed(2)}`, n.x, n.y + r + fontSize + 4 / globalScale);
      }
    },
    [hover?.id, selectedId]
  );

  if (!nodes.length) {
    return (
      <div className="h-[480px] w-full rounded-xl border border-border flex flex-col items-center justify-center bg-gradient-to-b from-black/50 to-black/20 text-gray-500 px-6 text-center gap-2">
        <p className="text-sm font-medium text-gray-400">Fraud ring network</p>
        <p className="text-xs max-w-md">
          Start the stream — each flagged transaction links a <span className="text-red-400">device</span> hub to its IP,
          shipping address, and user. Rings cluster by suspicious device.
        </p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative h-[480px] w-full rounded-xl border border-border overflow-hidden bg-gradient-to-br from-[#0a0f1a] to-[#111827]">
      <ForceGraph2D
        ref={ref}
        width={size.w}
        height={size.h}
        graphData={graphData}
        nodeLabel={() => ""}
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          const r = (node.is_hub ? 10 : 7) + 8;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}
        linkColor={(l: any) => {
          const cid = l.cluster_id || l.source?.cluster_id || "ring_0";
          const c = clusterColor(cid);
          return `${c}88`;
        }}
        linkWidth={(l: any) => (l.source?.is_hub || l.target?.is_hub ? 2 : 1.2)}
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={0.85}
        linkDirectionalParticles={1}
        linkDirectionalParticleWidth={2}
        cooldownTicks={120}
        onEngineStop={() => ref.current?.zoomToFit(600, 100)}
        onNodeHover={(n: any) => setHover(n || null)}
        onNodeClick={(n: any) => onNodeClick?.(n as RingNode)}
        backgroundColor="rgba(0,0,0,0)"
      />
      {hover && (
        <div className="absolute bottom-3 left-3 z-10 bg-black/80 border border-border rounded-lg px-3 py-2 text-xs max-w-xs pointer-events-none">
          <div className="font-semibold text-gray-200">{ENTITY_LABELS[hover.type] || hover.type}</div>
          <div className="font-mono text-gray-400 truncate">{hover.label}</div>
          <div className={`num mt-1 ${riskColor(hover.risk)}`}>Risk {hover.risk.toFixed(3)} · {hover.txn_count} flagged txns</div>
          <div className="text-gray-500">{hover.user_count} users · ₹{hover.total_inr.toLocaleString("en-IN")}</div>
        </div>
      )}
    </div>
  );
}
