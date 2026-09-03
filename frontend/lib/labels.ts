export const PATTERN_LABELS: Record<string, string> = {
  fraud_card_testing: "Card testing",
  fraud_stolen_card_burst: "Stolen-card burst",
  fraud_structuring: "Amount structuring",
  unknown: "Unclassified",
};

export const ENTITY_LABELS: Record<string, string> = {
  device: "Device",
  ip: "IP address",
  address: "Shipping address",
};

export function patternLabel(key?: string | null): string {
  if (!key) return "—";
  return PATTERN_LABELS[key] || key.replace(/_/g, " ");
}

export function bandStyle(band: string): string {
  if (band === "flagged") return "bg-red-900/60 text-red-300 border-red-700";
  if (band === "review") return "bg-amber-900/50 text-amber-300 border-amber-700";
  return "bg-green-900/40 text-green-300 border-green-800";
}

export function riskColor(score: number): string {
  if (score < 0.3) return "text-risk-low";
  if (score < 0.7) return "text-risk-mid";
  return "text-risk-high";
}
