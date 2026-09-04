"use client";

import { useCallback, useEffect, useState } from "react";
import { api, wsUrl } from "@/lib/api";
import { bandStyle, patternLabel, riskColor } from "@/lib/labels";
import EntityRiskTable from "@/components/EntityRiskTable";
import FraudRingPanel from "@/components/FraudRingPanel";
import InspectDrawer from "@/components/InspectDrawer";
import MetricsChart from "@/components/MetricsChart";
import ThresholdChart from "@/components/ThresholdChart";
import type { RingNode } from "@/components/RingGraph";

type TxnPayload = {
  transaction: Record<string, unknown>;
  risk_score: number;
  threshold_used: number;
  decision_band: string;
  flagged: boolean;
  reasons: string[];
};

type DashboardSummary = {
  processed: number;
  decision_counts: Record<string, number>;
  pattern_counts: Record<string, number>;
  confusion: { tp: number; fp: number; fn: number; tn: number };
  precision: number;
  recall: number;
  f1: number;
  fraud_prevented_inr: number;
  false_positive_cost_inr: number;
  total_volume_inr: number;
  flagged_volume_inr: number;
  session_fraud_total: number;
  session_fraud_caught: number;
  session_fraud_rate: number;
  review_queue_size: number;
  top_entities: any[];
  recent_high_risk: any[];
  flagged_count: number;
  drift?: { aggregate_psi: number; is_drifting: boolean };
};

export default function Dashboard() {
  const [ticker, setTicker] = useState<TxnPayload[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [history, setHistory] = useState<{ processed: number; precision: number; recall: number }[]>([]);
  const [reviewQueue, setReviewQueue] = useState<any[]>([]);
  const [audit, setAudit] = useState<any>(null);
  const [offline, setOffline] = useState<any>(null);
  const [speed, setSpeed] = useState(30);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showModelCard, setShowModelCard] = useState(false);
  const [showAbout, setShowAbout] = useState(false);
  const [connected, setConnected] = useState(false);
  const [streamRunning, setStreamRunning] = useState(false);
  const [streamProgress, setStreamProgress] = useState({ index: 0, total: 0 });
  const [ringData, setRingData] = useState<{
    nodes: RingNode[];
    links: any[];
    clusters: any[];
    stats: { flagged_txns: number; active_rings: number; entities: number; links?: number };
  }>({ nodes: [], links: [], clusters: [], stats: { flagged_txns: 0, active_rings: 0, entities: 0 } });
  const [selectedRingNode, setSelectedRingNode] = useState<RingNode | null>(null);

  const refreshRings = useCallback(() => {
    api<any>("/api/rings").then(setRingData).catch(() => {});
  }, []);

  const refreshSummary = useCallback(() => {
    api<DashboardSummary>("/api/dashboard/summary").then(setSummary).catch(() => {});
  }, []);

  const refreshQueue = useCallback(() => {
    api<any[]>("/api/review-queue").then(setReviewQueue).catch(() => {});
  }, []);

  const syncLiveState = useCallback(async () => {
    try {
      const status = await api<any>("/api/stream/status");
      setStreamRunning(status.running);
      setStreamProgress({ index: status.index || 0, total: status.total || 0 });
      if (status.history?.length) setHistory(status.history);
      if (status.session_id) setSessionId(status.session_id);
      refreshSummary();
      refreshRings();
    } catch {
      /* backend starting */
    }
  }, [refreshSummary, refreshRings]);

  useEffect(() => {
    api<any>("/api/metrics/offline").then(setOffline).catch(() => {});
    syncLiveState();
    refreshQueue();
    refreshRings();

    const ws = new WebSocket(wsUrl());
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "connected" && msg.session_id) setSessionId(msg.session_id);
      if (msg.type === "transaction") {
        const p = msg.payload as TxnPayload;
        setTicker((t) => [p, ...t].slice(0, 100));
        if (msg.metrics) {
          setHistory((h) =>
            [
              ...h,
              {
                processed: msg.metrics.processed,
                precision: msg.metrics.precision,
                recall: msg.metrics.recall,
              },
            ].slice(-200)
          );
        }
        refreshSummary();
        if (msg.payload?.decision_band === "review" || msg.payload?.flagged) refreshRings();
        if (msg.payload?.decision_band === "review") refreshQueue();
        setStreamRunning(true);
      }
      if (msg.type === "drift") {
        setSummary((s) => (s ? { ...s, drift: msg.payload } : s));
      }
      if (msg.type === "stream_complete") {
        setStreamRunning(false);
        refreshQueue();
        syncLiveState();
      }
    };

    const poll = setInterval(syncLiveState, 2000);
    const queuePoll = setInterval(refreshQueue, 5000);
    return () => {
      ws.close();
      clearInterval(poll);
      clearInterval(queuePoll);
    };
  }, [refreshQueue, refreshRings, refreshSummary, syncLiveState]);

  const startStream = async () => {
    try {
      await api("/api/stream/reset", { method: "POST" });
      const res = await api<any>(`/api/stream/start?speed=${speed}`, { method: "POST" });
      setSessionId(res.session_id);
      setStreamRunning(true);
      setStreamProgress({ index: 0, total: res.transactions || 0 });
      setTicker([]);
      setHistory([]);
      setRingData({ nodes: [], links: [], clusters: [], stats: { flagged_txns: 0, active_rings: 0, entities: 0 } });
      setSelectedRingNode(null);
      refreshQueue();
      refreshSummary();
      refreshRings();
    } catch {
      alert("Failed to start stream — check backend logs.");
    }
  };

  const resetStream = async () => {
    await api("/api/stream/reset", { method: "POST" });
    setStreamRunning(false);
    setStreamProgress({ index: 0, total: 0 });
    setTicker([]);
    setHistory([]);
    setRingData({ nodes: [], links: [], clusters: [], stats: { flagged_txns: 0, active_rings: 0, entities: 0 } });
    setSelectedRingNode(null);
    setSummary(null);
    refreshQueue();
    refreshSummary();
    refreshRings();
  };

  const openTxn = async (txnId: string) => {
    const data = await api<any>(`/api/audit/${txnId}`);
    setAudit(data);
  };

  const reviewAction = async (txnId: string, action: "approve" | "reject") => {
    await api(`/api/review-queue/${txnId}/${action}`, { method: "POST" });
    refreshQueue();
    openTxn(txnId);
  };

  const s = summary;
  const dc = s?.decision_counts || { allow: 0, review: 0, flagged: 0 };
  const conf = s?.confusion || { tp: 0, fp: 0, fn: 0, tn: 0 };
  const drift = s?.drift || { aggregate_psi: 0, is_drifting: false };
  const held = offline?.heldout_evaluation;
  const patterns = s?.pattern_counts || {};

  return (
    <div className="min-h-screen p-4 md:p-6 max-w-[1600px] mx-auto">
      <header className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">RingWatch</h1>
          <p className="text-sm text-gray-400">
            Real-time fraud risk operations · coordinated ring detection
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs px-2 py-1 rounded ${connected ? "bg-green-900/50 text-green-400" : "bg-red-900/50 text-red-400"}`}>
            {connected ? "Live" : "Offline"}
          </span>
          {sessionId && <span className="text-xs text-gray-500 font-mono">session {sessionId}</span>}
          {streamRunning && (
            <span className="text-xs text-amber-400 font-mono">
              {streamProgress.index}/{streamProgress.total}
            </span>
          )}
          <input type="range" min={5} max={50} value={speed} onChange={(e) => setSpeed(+e.target.value)} className="w-24" />
          <span className="text-xs text-gray-500">{speed} tx/s</span>
          <button onClick={startStream} className="px-3 py-1.5 bg-green-700 hover:bg-green-600 rounded text-sm">Start</button>
          <button onClick={() => api("/api/stream/pause", { method: "POST" })} className="px-3 py-1.5 bg-amber-800 hover:bg-amber-700 rounded text-sm">Pause</button>
          <button onClick={resetStream} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm">Reset</button>
          <button onClick={() => setShowModelCard(true)} className="px-3 py-1.5 border border-border rounded text-sm">Model Card</button>
          <button onClick={() => setShowAbout(true)} className="px-3 py-1.5 border border-border rounded text-sm">About</button>
        </div>
      </header>

      {/* Held-out evaluation — primary credible metrics */}
      <div className="card mb-4 border-amber-800/40 bg-amber-950/10">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h2 className="text-sm font-semibold text-amber-200">Held-out test set performance</h2>
            <p className="text-xs text-gray-500">
              Single evaluation on transactions_test_HELDOUT_v2.csv — not live replay
            </p>
          </div>
          {held?.confusion_matrix && (
            <span className="text-xs text-gray-400 font-mono">
              TP {held.confusion_matrix.tp} · FP {held.confusion_matrix.fp} · FN {held.confusion_matrix.fn} · TN {held.confusion_matrix.tn}
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Kpi label="Precision" value={held ? held.precision.toFixed(3) : "—"} accent="text-amber-300" />
          <Kpi label="Recall" value={held ? held.recall.toFixed(3) : "—"} accent="text-amber-300" />
          <Kpi label="F1" value={held ? held.f1.toFixed(3) : "—"} accent="text-amber-300" />
          <Kpi label="ROC-AUC" value={held ? held.roc_auc.toFixed(3) : "—"} />
          <Kpi
            label="Threshold range"
            value={held ? `${held.threshold_min}–${held.threshold_max}` : "—"}
            sub="dynamic per txn"
          />
        </div>
      </div>

      {/* Operational KPIs — live replay session */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
        <Kpi label="Processed" value={String(s?.processed ?? 0)} />
        <Kpi label="Allowed" value={String(dc.allow ?? 0)} accent="text-green-400" />
        <Kpi label="Under review" value={String(dc.review ?? 0)} accent="text-amber-400" />
        <Kpi label="Auto-flagged" value={String(dc.flagged ?? 0)} accent="text-red-400" />
        <Kpi
          label="Fraud caught"
          value={`${s?.session_fraud_caught ?? 0}/${s?.session_fraud_total ?? 0}`}
          sub={s?.session_fraud_total ? `${((s.session_fraud_rate || 0) * 100).toFixed(0)}% recall` : "session"}
          accent="text-risk-low"
        />
        <Kpi label="Review queue" value={String(s?.review_queue_size ?? 0)} accent="text-amber-300" />
      </div>

      {/* Financial + session accuracy */}
      <div className="grid md:grid-cols-4 gap-3 mb-4">
        <div className="card">
          <div className="text-xs text-gray-500">Fraud prevented (session)</div>
          <div className="text-xl num text-risk-low">
            ₹{(s?.fraud_prevented_inr ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
          </div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-500">False-positive cost</div>
          <div className="text-xl num text-risk-high">
            ₹{(s?.false_positive_cost_inr ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
          </div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-500">Flagged volume</div>
          <div className="text-xl num">
            ₹{(s?.flagged_volume_inr ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
          </div>
          <p className="text-[10px] text-gray-500 mt-1">
            of ₹{(s?.total_volume_inr ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })} total
          </p>
        </div>
        <div className="card">
          <div className="text-xs text-gray-500">Session precision / recall</div>
          <div className="text-xl num">
            {(s?.precision ?? 0).toFixed(3)} / {(s?.recall ?? 0).toFixed(3)}
          </div>
          <p className="text-[10px] text-gray-500 mt-1">
            Live replay only · includes training data · not for reporting
          </p>
        </div>
      </div>

      {(s?.processed ?? 0) > 0 && (
        <div className="card mb-4 border-border/60">
          <h2 className="text-xs font-medium text-gray-400 mb-2 uppercase tracking-wide">
            Current session (replay with labels)
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <span className="text-gray-500">Confusion: </span>
              <span className="num text-green-400">TP {conf.tp}</span>
              <span className="text-gray-600"> · </span>
              <span className="num text-red-400">FP {conf.fp}</span>
              <span className="text-gray-600"> · </span>
              <span className="num text-orange-400">FN {conf.fn}</span>
            </div>
            <div><span className="text-gray-500">Fraud caught: </span>{s?.session_fraud_caught}/{s?.session_fraud_total}</div>
            <div><span className="text-gray-500">Fraud prevented: </span>₹{(s?.fraud_prevented_inr ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</div>
            <div><span className="text-gray-500">FP cost: </span>₹{(s?.false_positive_cost_inr ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</div>
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-4 mb-4">
        {/* Main: suspicious entities */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-medium text-gray-200">Suspicious entities</h2>
              <p className="text-xs text-gray-500">Devices, IPs, and addresses linked to flagged activity</p>
            </div>
            <span className="text-xs text-gray-500">{s?.top_entities?.length ?? 0} tracked</span>
          </div>
          <EntityRiskTable entities={s?.top_entities ?? []} />
        </div>

        {/* Side panel */}
        <div className="space-y-4">
          <div className="card">
            <h2 className="text-sm font-medium text-gray-200 mb-3">Detection breakdown</h2>
            {Object.keys(patterns).length === 0 ? (
              <p className="text-sm text-gray-500">Fraud patterns appear as rings are caught</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(patterns).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm">
                    <span className="text-gray-300">{patternLabel(k)}</span>
                    <span className="num font-semibold text-amber-400">{v}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <h2 className="text-sm font-medium text-gray-200 mb-3">Confusion matrix (session)</h2>
            <div className="grid grid-cols-2 gap-2 text-center text-xs">
              <ConfCell label="True positive" value={conf.tp} color="text-green-400" />
              <ConfCell label="False positive" value={conf.fp} color="text-red-400" />
              <ConfCell label="False negative" value={conf.fn} color="text-orange-400" />
              <ConfCell label="True negative" value={conf.tn} color="text-gray-400" />
            </div>
          </div>

          <div className="card">
            <h2 className="text-sm font-medium text-gray-200 mb-2">Drift monitor (PSI)</h2>
            <div className={`text-2xl num ${drift.is_drifting ? "text-risk-high" : "text-risk-low"}`}>
              {drift.aggregate_psi?.toFixed(4) ?? "0.0000"}
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {drift.is_drifting ? "Distribution shift detected (>0.2)" : "Stable vs training baseline"}
            </p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mb-4">
        <div className="card">
          <h2 className="text-sm font-medium text-gray-200 mb-2">Session precision / recall (replay)</h2>
          <p className="text-[10px] text-gray-500 mb-2">Cumulative over current stream — expect variance early on</p>
          <MetricsChart data={history} />
        </div>
        <div className="card">
          <h2 className="text-sm font-medium text-gray-200 mb-2">Dynamic threshold vs amount</h2>
          <ThresholdChart />
          <p className="text-[10px] text-gray-500 mt-1">Higher ₹ and ring velocity → lower review bar</p>
        </div>
      </div>

      {/* Live ticker + high-risk / review */}
      <div className="grid lg:grid-cols-3 gap-4 mb-4">
        <div className="card max-h-[420px] overflow-y-auto lg:col-span-1">
          <h2 className="text-sm font-medium text-gray-200 mb-3 sticky top-0 bg-panel pb-2 z-10">
            Live transaction feed
            <span className="text-gray-500 font-normal ml-2">({ticker.length})</span>
          </h2>
          {ticker.length === 0 && (
            <p className="text-sm text-gray-500">Waiting for stream… click Start</p>
          )}
          {ticker.map((t, i) => {
            const txn = t.transaction as Record<string, unknown>;
            const txnId = String(txn.transaction_id ?? "");
            return (
              <button
                key={`${txnId}-${i}`}
                onClick={() => openTxn(txnId)}
                className="w-full text-left py-2 border-b border-border/50 hover:bg-white/5 px-1"
              >
                <div className="flex justify-between text-sm gap-2">
                  <span className="font-mono text-gray-400 truncate">{txnId}</span>
                  <span className={`num shrink-0 ${riskColor(t.risk_score)}`}>{t.risk_score.toFixed(3)}</span>
                </div>
                <div className="flex justify-between text-xs text-gray-500 mt-0.5">
                  <span>₹{Number(txn.amount_inr).toFixed(0)} · {t.decision_band}</span>
                  <span className="num">thr {t.threshold_used.toFixed(2)}</span>
                </div>
              </button>
            );
          })}
        </div>

        <div className="card max-h-[420px] overflow-y-auto lg:col-span-1">
          <h2 className="text-sm font-medium text-gray-200 mb-3 sticky top-0 bg-panel pb-2">
            High-risk transactions
          </h2>
          {!s?.recent_high_risk?.length && (
            <p className="text-sm text-gray-500">No review/flagged transactions yet — start the stream</p>
          )}
          {[...(s?.recent_high_risk ?? [])].reverse().map((t) => (
            <button
              key={t.transaction_id}
              onClick={() => openTxn(t.transaction_id)}
              className="w-full text-left py-3 border-b border-border/50 hover:bg-white/5 px-1"
            >
              <div className="flex justify-between items-center gap-2">
                <span className="font-mono text-sm text-gray-300">{t.transaction_id}</span>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded border ${bandStyle(t.decision_band)}`}>
                    {t.decision_band}
                  </span>
                  <span className={`num text-sm font-semibold ${riskColor(t.risk_score)}`}>
                    {t.risk_score?.toFixed(3)}
                  </span>
                </div>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                ₹{Number(t.amount_inr).toLocaleString("en-IN")} · device {t.device_id} · {t.reasons?.[0]}
              </div>
            </button>
          ))}
        </div>

        <div className="card max-h-[420px] overflow-y-auto lg:col-span-1">
          <h2 className="text-sm font-medium text-gray-200 mb-3 sticky top-0 bg-panel pb-2">
            Human review queue
            <span className="text-gray-500 font-normal ml-2">({reviewQueue.length} pending)</span>
          </h2>
          {reviewQueue.length === 0 && (
            <p className="text-sm text-gray-500">Borderline transactions awaiting analyst decision</p>
          )}
          {reviewQueue.map((item) => (
            <div key={item.transaction_id} className="py-3 border-b border-border/50">
              <div className="flex justify-between text-sm mb-1">
                <span className="font-mono">{item.transaction_id}</span>
                <span className={`num font-semibold ${riskColor(item.risk_score)}`}>
                  {item.risk_score?.toFixed(3)}
                </span>
              </div>
              <ul className="text-xs text-gray-400 list-disc pl-4 space-y-0.5">
                {(item.reasons || []).map((r: string, j: number) => (
                  <li key={j}>{r}</li>
                ))}
              </ul>
              <div className="flex gap-2 mt-2">
                <button onClick={() => reviewAction(item.transaction_id, "approve")} className="text-xs px-2 py-1 bg-green-800 rounded hover:bg-green-700">Approve</button>
                <button onClick={() => reviewAction(item.transaction_id, "reject")} className="text-xs px-2 py-1 bg-red-900 rounded hover:bg-red-800">Reject</button>
                <button onClick={() => openTxn(item.transaction_id)} className="text-xs px-2 py-1 border border-border rounded hover:bg-white/5">Inspect</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <FraudRingPanel
        data={ringData}
        selectedNode={selectedRingNode}
        onNodeClick={setSelectedRingNode}
        onInspectTxn={openTxn}
      />

      {audit && <InspectDrawer audit={audit} onClose={() => setAudit(null)} />}

      {showModelCard && (
        <Modal title="Model Card (held-out evaluation)" onClose={() => setShowModelCard(false)}>
          <div className="space-y-3 text-sm text-gray-300">
            <p className="text-xs text-amber-400/90 bg-amber-900/20 border border-amber-800/40 rounded p-2">
              Primary metrics are from a single held-out test run — not live session replay.
            </p>
            <p><strong>Version:</strong> {offline?.model_version}</p>
            <p><strong>Ensemble:</strong> XGBoost (37.5%) + LightGBM (37.5%) + Isolation Forest (25%)</p>
            <p><strong>Features ({offline?.features_used?.length ?? 0}):</strong></p>
            <ul className="text-xs text-gray-400 list-disc pl-5 max-h-32 overflow-y-auto">
              {(offline?.features_used ?? []).map((f: string) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            {held && (
              <>
                <p><strong>Precision:</strong> {held.precision} · <strong>Recall:</strong> {held.recall} · <strong>F1:</strong> {held.f1}</p>
                <p><strong>ROC-AUC:</strong> {held.roc_auc}</p>
                <p><strong>Confusion:</strong> TP {held.confusion_matrix?.tp}, FP {held.confusion_matrix?.fp}, FN {held.confusion_matrix?.fn}, TN {held.confusion_matrix?.tn}</p>
                <p><strong>FP cost (₹):</strong> {held.false_positive_cost_inr?.toLocaleString()}</p>
                <p><strong>Threshold range:</strong> {held.threshold_min} – {held.threshold_max}</p>
              </>
            )}
            {held?.hard_negative_fp_rates && (
              <>
                <p className="font-medium text-gray-200">Hard-negative false positive rates (held-out)</p>
                <ul className="text-xs text-gray-400 space-y-1">
                  {Object.entries(held.hard_negative_fp_rates).map(([k, v]: [string, any]) => (
                    <li key={k}>{k}: {(v.fp_rate * 100).toFixed(1)}% ({v.false_positives}/{v.legit_rows})</li>
                  ))}
                </ul>
              </>
            )}
            {offline?.train_hard_negative_fp_rates && (
              <>
                <p className="font-medium text-gray-200">Hard-negative FP rates (train set stress check)</p>
                <ul className="text-xs text-gray-400 space-y-1">
                  {Object.entries(offline.train_hard_negative_fp_rates).map(([k, v]: [string, any]) => (
                    <li key={k}>{k}: {(v.fp_rate * 100).toFixed(1)}% ({v.false_positives}/{v.legit_rows})</li>
                  ))}
                </ul>
              </>
            )}
            <p className="text-gray-400">{offline?.known_limitations}</p>
            <p className="text-xs text-gray-500">Leakage audit: ml/leakage_audit.md</p>
          </div>
        </Modal>
      )}

      {showAbout && (
        <Modal title="What RingWatch does" onClose={() => setShowAbout(false)}>
          <div className="space-y-3 text-sm text-gray-300">
            <p><strong>Card testing:</strong> Many small payments from same device/IP — stolen card probes.</p>
            <p><strong>Stolen-card burst:</strong> Multiple users, same shipping address, mid/large amounts.</p>
            <p><strong>Structuring:</strong> Amounts clustered just under ₹10,000 review threshold.</p>
            <p className="text-gray-400 pt-2 border-t border-border">
              Defense-only: score, explain, queue for human review. No payment blocking in this demo.
              Telegram alerts fire on review/flagged transactions when configured.
            </p>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="card">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-2xl num font-semibold ${accent || ""}`}>{value}</div>
      {sub && <div className="text-[10px] text-gray-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function ConfCell({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-black/30 rounded-lg p-2 border border-border/40">
      <div className="text-gray-500 mb-1">{label}</div>
      <div className={`num text-lg font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="card max-w-lg w-full max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg mb-4">{title}</h2>
        {children}
        <button onClick={onClose} className="mt-4 text-sm text-gray-400 hover:text-white">Close</button>
      </div>
    </div>
  );
}
