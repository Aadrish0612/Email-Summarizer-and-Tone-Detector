// UrgencyMeter.jsx
const URGENCY_COLORS = {
  1: "#22c55e",   // green
  2: "#84cc16",   // lime green
  3: "#eab308",   // light yellow
  4: "#f97316",   // orange
  5: "#ef4444",   // red
  6: "#b91c1c",   // deep red
};

export function UrgencyMeter({ level }) {
  const clamped = Math.min(6, Math.max(1, level || 1));
  const color = URGENCY_COLORS[clamped];

  return (
    <div style={{ display: "flex", gap: 2 }}>
      {Array.from({ length: 6 }).map((_, i) => {
        const filled = i < clamped;
        return (
          <div
            key={i}
            style={{
              width: 10,
              height: 16,
              borderRadius: 2,
              border: "1px solid #ccc",
              backgroundColor: filled ? color : "#e5e7eb",
            }}
          />
        );
      })}
    </div>
  );
}
