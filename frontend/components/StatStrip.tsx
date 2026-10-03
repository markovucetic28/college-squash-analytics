import type { ReactNode } from "react";

export default function StatStrip({ items }: { items: { label: ReactNode; value: string }[] }) {
  return <div className="stat-strip">{items.map((item) => (
    <div key={String(item.label)}><span>{item.label}</span><strong>{item.value}</strong></div>
  ))}</div>;
}
