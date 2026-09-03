"use client";

import { Line, LineChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";

export default function ThresholdChart() {
  const data = Array.from({ length: 50 }, (_, i) => {
    const amount = i * 600;
    const ring = i > 35 ? 0.8 : 0.1;
    const threshold = Math.max(0.28, Math.min(0.85, 0.82 - 0.4 * (amount / 15000) - 0.2 * ring));
    return { amount, threshold };
  });

  return (
    <div className="card">
      <h3 className="text-sm text-gray-400 mb-2">Dynamic threshold vs amount</h3>
      <ResponsiveContainer width="100%" height={100}>
        <LineChart data={data}>
          <XAxis dataKey="amount" tick={{ fill: "#6b7280", fontSize: 10 }} tickFormatter={(v) => `₹${v}`} />
          <YAxis domain={[0.2, 0.9]} tick={{ fill: "#6b7280", fontSize: 10 }} />
          <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151" }} />
          <Line type="monotone" dataKey="threshold" stroke="#60a5fa" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
      <p className="text-xs text-gray-500 mt-1">Higher ₹ → lower bar; ring velocity also lowers threshold</p>
    </div>
  );
}
