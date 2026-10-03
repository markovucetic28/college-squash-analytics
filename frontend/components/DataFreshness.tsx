"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

export default function DataFreshness() {
  const [updated, setUpdated] = useState<string | null>(null);
  useEffect(() => {
    fetch(`${API_URL}/api/status`).then((response) => response.ok ? response.json() : null)
      .then((data) => setUpdated(data?.last_successful_refresh || null)).catch(() => {});
  }, []);
  if (!updated) return null;
  const label = new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  }).format(new Date(updated));
  return <span className="data-freshness">Data updated {label}</span>;
}
