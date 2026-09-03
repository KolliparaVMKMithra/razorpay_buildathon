"use client";

import { bandStyle, patternLabel, riskColor } from "@/lib/labels";

type Props = {
  audit: any;
  onClose: () => void;
};

export default function InspectDrawer({ audit, onClose }: Props) {
  if (!audit?.transaction) return null;
  const t = audit.transaction;

  return (
    <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-[#0d1117] border-l border-border p-6 shadow-2xl z-50 overflow-y-auto">
      <button onClick={onClose} className="text-gray-400 text-sm mb-4 hover:text-white">
        ← Close
      </button>

      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-semibold font-mono">{t.transaction_id}</h2>
          <p className="text-xs text-gray-500 mt-1">{t.timestamp}</p>
        </div>
        <span className={`text-xs px-2 py-1 rounded border ${bandStyle(t.decision_band)}`}>
          {t.decision_band}
        </span>
      </div>

      <div className="mb-4">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-400">Risk score</span>
          <span className={`num font-semibold ${riskColor(t.risk_score)}`}>
            {t.risk_score?.toFixed(3)}
          </span>
        </div>
        <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-amber-500 to-red-500"
            style={{ width: `${Math.min(100, (t.risk_score || 0) * 100)}%` }}
          />
        </div>
        <p className="text-xs text-gray-500 mt-1">
          Dynamic threshold: <span className="num">{t.threshold_used?.toFixed(3)}</span>
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
        <Info label="Amount" value={`₹${Number(t.amount_inr).toLocaleString("en-IN")}`} />
        <Info label="Payment" value={t.payment_method || "—"} />
        <Info label="Device" value={t.device_id} mono />
        <Info label="IP" value={t.ip_address} mono />
        <Info label="Address ID" value={t.shipping_address_id} mono />
        <Info label="City" value={t.shipping_city || "—"} />
      </div>

      {t.reasons?.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">Why flagged</h3>
          <ul className="space-y-2">
            {t.reasons.map((r: string, i: number) => (
              <li key={i} className="text-sm text-gray-300 bg-black/30 border border-border/50 rounded-lg px-3 py-2">
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {t.is_fraud != null && (
        <div className="mb-4 p-3 rounded-lg border border-border/60 bg-black/20">
          <p className="text-xs text-gray-500 mb-1">Replay ground truth (demo labels only)</p>
          <p className="text-sm">
            {t.is_fraud ? (
              <span className="text-red-400">
                Confirmed fraud — {patternLabel(t.cluster_type)}
              </span>
            ) : (
              <span className="text-green-400">Legitimate transaction</span>
            )}
          </p>
        </div>
      )}

      <div>
        <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">Audit trail</h3>
        {(audit.audit_trail || []).length === 0 && (
          <p className="text-sm text-gray-500">No audit events yet</p>
        )}
        {(audit.audit_trail || []).map((e: any, i: number) => (
          <div key={i} className="text-xs border-l-2 border-amber-600/70 pl-3 mb-3">
            <div className="text-gray-200">{e.action}</div>
            <div className="text-gray-500">{e.actor} · {e.created_at}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-black/25 rounded-lg px-3 py-2 border border-border/40">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className={`text-sm truncate ${mono ? "font-mono text-xs" : ""}`} title={value}>
        {value}
      </div>
    </div>
  );
}
