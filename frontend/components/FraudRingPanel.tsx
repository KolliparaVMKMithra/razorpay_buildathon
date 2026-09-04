"use client";

import { patternLabel, riskColor } from "@/lib/labels";
import RingGraph, { RingCluster, RingLink, RingNode } from "@/components/RingGraph";

const LEGEND = [
  { type: "device", label: "Device (ring hub)", color: "#ef4444" },
  { type: "ip", label: "IP address", color: "#f97316" },
  { type: "address", label: "Shipping address", color: "#eab308" },
  { type: "user", label: "User account", color: "#22c55e" },
];

export default function FraudRingPanel({
  data,
  selectedNode,
  onNodeClick,
  onInspectTxn,
}: {
  data: {
    nodes: RingNode[];
    links: RingLink[];
    clusters: RingCluster[];
    stats: { flagged_txns: number; active_rings: number; entities: number; links?: number };
  };
  selectedNode: RingNode | null;
  onNodeClick: (n: RingNode) => void;
  onInspectTxn?: (txnId: string) => void;
}) {
  const { nodes, links, clusters, stats } = data;

  return (
    <div className="card mt-4">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">Fraud ring network</h2>
          <p className="text-sm text-gray-500 mt-1 max-w-2xl">
            Each <span className="text-red-400 font-medium">device hub</span> connects to IPs, addresses, and users
            involved in the same flagged transaction. Colored rings = separate coordinated clusters detected this session.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <StatPill label="Flagged txns" value={stats.flagged_txns} />
          <StatPill label="Active rings" value={stats.active_rings} accent="text-amber-400" />
          <StatPill label="Entities" value={stats.entities} />
          <StatPill label="Links" value={stats.links ?? links.length} />
        </div>
      </div>

      <div className="grid lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3">
          <RingGraph
            nodes={nodes}
            links={links}
            clusters={clusters}
            selectedId={selectedNode?.id}
            onNodeClick={onNodeClick}
          />
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-black/30 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Legend</h3>
            <ul className="space-y-2">
              {LEGEND.map((item) => (
                <li key={item.type} className="flex items-center gap-2 text-xs text-gray-300">
                  <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: item.color }} />
                  {item.label}
                </li>
              ))}
            </ul>
            <p className="text-[10px] text-gray-500 mt-3 border-t border-border/50 pt-2">
              Dashed ring = device hub · Solid lines = same flagged transaction
            </p>
          </div>

          <div className="rounded-xl border border-border bg-black/30 p-3 max-h-[200px] overflow-y-auto">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
              Detected rings ({clusters.length})
            </h3>
            {clusters.length === 0 && (
              <p className="text-xs text-gray-500">No rings yet</p>
            )}
            {clusters.map((c, i) => (
              <button
                key={c.id}
                type="button"
                onClick={() => {
                  const hub = nodes.find((n) => n.id === c.hub_id);
                  if (hub) onNodeClick(hub);
                }}
                className="w-full text-left py-2 border-b border-border/40 last:border-0 hover:bg-white/5 rounded px-1"
              >
                <div className="flex justify-between items-center gap-2">
                  <span className="text-xs font-medium text-gray-200">
                    Ring {i + 1} · device …{c.hub_label.slice(-8)}
                  </span>
                  <span className={`num text-xs ${riskColor(c.max_risk)}`}>{c.max_risk.toFixed(2)}</span>
                </div>
                <div className="text-[10px] text-gray-500 mt-0.5">
                  {c.txn_count} txns · ₹{c.volume_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  {c.pattern ? ` · ${patternLabel(c.pattern)}` : ""}
                </div>
                <div className="text-[10px] text-gray-600 mt-0.5">
                  {Object.entries(c.members)
                    .map(([t, n]) => `${n} ${t}${n > 1 ? "s" : ""}`)
                    .join(" · ")}
                </div>
              </button>
            ))}
          </div>

          {selectedNode && (
            <div className="rounded-xl border border-amber-800/50 bg-amber-950/20 p-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-amber-500/80 mb-2">Selected entity</h3>
              <p className="text-sm font-mono text-gray-200 break-all">{selectedNode.label}</p>
              <p className="text-xs text-gray-500 mt-1 capitalize">{selectedNode.type}{selectedNode.is_hub ? " · hub" : ""}</p>
              <dl className="grid grid-cols-2 gap-x-2 gap-y-1 mt-2 text-xs">
                <dt className="text-gray-500">Risk</dt>
                <dd className={`num text-right ${riskColor(selectedNode.risk)}`}>{selectedNode.risk.toFixed(3)}</dd>
                <dt className="text-gray-500">Flagged txns</dt>
                <dd className="num text-right">{selectedNode.txn_count}</dd>
                <dt className="text-gray-500">Users</dt>
                <dd className="num text-right">{selectedNode.user_count}</dd>
                <dt className="text-gray-500">Volume</dt>
                <dd className="num text-right">₹{selectedNode.total_inr.toLocaleString("en-IN")}</dd>
              </dl>
              {selectedNode.patterns?.length > 0 && (
                <p className="text-[10px] text-amber-400/90 mt-2">
                  Pattern: {selectedNode.patterns.map(patternLabel).join(", ")}
                </p>
              )}
            </div>
          )}

          {selectedNode && links.filter((l) => l.source === selectedNode.id || l.target === selectedNode.id).length > 0 && (
            <div className="rounded-xl border border-border bg-black/30 p-3 max-h-[140px] overflow-y-auto">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Linked transactions</h3>
              {links
                .filter((l) => l.source === selectedNode.id || l.target === selectedNode.id)
                .slice(0, 8)
                .map((l) => (
                  <button
                    key={`${l.transaction_id}-${l.relation}`}
                    type="button"
                    onClick={() => l.transaction_id && onInspectTxn?.(l.transaction_id)}
                    className="w-full text-left text-[10px] py-1.5 border-b border-border/30 hover:bg-white/5 font-mono"
                  >
                    {l.transaction_id} · ₹{Number(l.amount_inr || 0).toFixed(0)} · risk {(l.risk_score || 0).toFixed(2)}
                  </button>
                ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatPill({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: string;
}) {
  return (
    <div className="bg-black/40 border border-border/60 rounded-lg px-3 py-1.5">
      <div className="text-[10px] text-gray-500">{label}</div>
      <div className={`num text-sm font-semibold ${accent || "text-gray-200"}`}>{value}</div>
    </div>
  );
}
