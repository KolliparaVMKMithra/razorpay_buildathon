"use client";

import { ENTITY_LABELS, patternLabel, riskColor } from "@/lib/labels";

type Entity = {
  key: string;
  type: string;
  id: string;
  txn_count: number;
  user_count: number;
  total_inr: number;
  max_risk: number;
  patterns: string[];
};

export default function EntityRiskTable({
  entities,
  onSelect,
}: {
  entities: Entity[];
  onSelect?: (entity: Entity) => void;
}) {
  if (!entities.length) {
    return (
      <p className="text-sm text-gray-500 py-8 text-center">
        Suspicious devices, IPs, and addresses will appear here when review/flagged transactions are detected.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-gray-500 border-b border-border">
            <th className="pb-2 pr-3 font-medium">Type</th>
            <th className="pb-2 pr-3 font-medium">Entity</th>
            <th className="pb-2 pr-3 font-medium num">Flagged txns</th>
            <th className="pb-2 pr-3 font-medium num">Users</th>
            <th className="pb-2 pr-3 font-medium num">Volume</th>
            <th className="pb-2 pr-3 font-medium num">Max risk</th>
            <th className="pb-2 font-medium">Pattern</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((e) => (
            <tr
              key={e.key}
              className="border-b border-border/40 hover:bg-white/5 cursor-pointer"
              onClick={() => onSelect?.(e)}
            >
              <td className="py-2.5 pr-3">
                <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-300">
                  {ENTITY_LABELS[e.type] || e.type}
                </span>
              </td>
              <td className="py-2.5 pr-3 font-mono text-xs text-gray-300 max-w-[140px] truncate" title={e.id}>
                {e.id}
              </td>
              <td className="py-2.5 pr-3 num">{e.txn_count}</td>
              <td className="py-2.5 pr-3 num">{e.user_count}</td>
              <td className="py-2.5 pr-3 num">₹{e.total_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</td>
              <td className={`py-2.5 pr-3 num font-semibold ${riskColor(e.max_risk)}`}>
                {e.max_risk.toFixed(3)}
              </td>
              <td className="py-2.5 text-xs text-gray-400">
                {e.patterns.length ? e.patterns.map(patternLabel).join(", ") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
