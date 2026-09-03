"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

type Node = { id: string; type: string; risk?: number; flagged?: boolean; label?: string };
type Link = { source: string; target: string; transaction_id?: string };

const TYPE_COLORS: Record<string, string> = {
  device: "#ef4444",
  ip: "#f97316",
  address: "#f59e0b",
  user: "#22c55e",
};

export default function RingGraph({
  nodes,
  links,
  onNodeClick,
}: {
  nodes: Node[];
  links: Link[];
  onNodeClick?: (id: string) => void;
}) {
  const ref = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 600, h: 360 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setSize({ w: el.clientWidth || 600, h: el.clientHeight || 360 });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const graphData = useMemo(() => {
    const nodeMap = new Map(
      nodes.map((n) => [
        n.id,
        {
          ...n,
          name: n.label || n.id.split(":").slice(1).join(":") || n.id,
        },
      ])
    );
    const validLinks = links
      .map((l) => ({
        source: typeof l.source === "string" ? l.source : (l as any).source?.id,
        target: typeof l.target === "string" ? l.target : (l as any).target?.id,
      }))
      .filter((l) => l.source && l.target && nodeMap.has(l.source) && nodeMap.has(l.target));

    return { nodes: Array.from(nodeMap.values()), links: validLinks };
  }, [nodes, links]);

  useEffect(() => {
    if (!ref.current || !graphData.nodes.length) return;
    ref.current.d3Force("charge")?.strength(-180);
    ref.current.d3Force("link")?.distance(60);
    const timer = setTimeout(() => {
      ref.current?.zoomToFit(500, 80);
    }, 400);
    return () => clearTimeout(timer);
  }, [graphData.nodes.length, graphData.links.length, size.w]);

  if (!nodes.length) {
    return (
      <div className="h-[360px] w-full rounded-xl border border-border flex items-center justify-center bg-black/40 text-gray-500 text-sm px-4 text-center">
        Flagged ring clusters will appear here as the stream detects them
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative h-[360px] w-full rounded-xl border border-border overflow-hidden bg-black/40">
      <div className="absolute top-2 left-2 z-10 text-xs text-gray-400 bg-black/60 px-2 py-1 rounded">
        {graphData.nodes.length} nodes · {graphData.links.length} links
      </div>
      <ForceGraph2D
        ref={ref}
        width={size.w}
        height={size.h}
        graphData={graphData}
        nodeLabel={(n: any) => `${n.type}: ${n.name}`}
        nodeVal={(n: any) => 6 + (n.risk || 0) * 8}
        nodeRelSize={4}
        linkWidth={1.5}
        linkDirectionalParticles={1}
        linkDirectionalParticleWidth={2}
        cooldownTicks={100}
        onEngineStop={() => ref.current?.zoomToFit(500, 80)}
        nodeColor={(n: any) => TYPE_COLORS[n.type] || "#ef4444"}
        linkColor={() => "rgba(239,68,68,0.35)"}
        backgroundColor="rgba(0,0,0,0)"
        onNodeClick={(n: any) => onNodeClick?.(n.id)}
      />
    </div>
  );
}
