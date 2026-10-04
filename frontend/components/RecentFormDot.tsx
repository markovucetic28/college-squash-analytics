import type { RecentForm } from "@/lib/types";

export default function RecentFormDot({ form }: { form?: RecentForm | null }) {
  const value = form || {
    state: "limited" as const, label: "Limited recent data",
    description: "Not enough recent rated matches to assess form.", score: null, matches: 0,
  };
  const accessible = `Recent form: ${value.label.toLowerCase()}. ${value.description}`;
  return <span className={`recent-form form-${value.state}`} role="img"
    aria-label={accessible} title={`${value.label} — ${value.description}`}>
    <span aria-hidden="true" className="recent-form-dot" />
    <span className="recent-form-text">{value.label}</span>
  </span>;
}
