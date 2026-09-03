"use client";

import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function MetricsChart({ data }: { data: { processed: number; precision: number; recall: number }[] }) {
  if (!data.length) {
    return <div className="h-32 flex items-center justify-center text-gray-500 text-sm">Start stream to see live metrics</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={120}>
      <LineChart data={data}>
        <XAxis dataKey="processed" hide />
        <YAxis domain={[0, 1]} tick={{ fill: "#6b7280", fontSize: 10 }} />
        <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151" }} />
        <Line type="monotone" dataKey="precision" stroke="#22c55e" dot={false} strokeWidth={2} />
        <Line type="monotone" dataKey="recall" stroke="#f59e0b" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}
