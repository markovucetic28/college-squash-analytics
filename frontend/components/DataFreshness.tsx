"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

export default function DataFreshness() {
  const [status, setStatus] = useState<{last_successful_refresh?:string|null;last_schedule_refresh?:string|null;last_rating_refresh?:string|null;prediction_data_status?:string|null}|null>(null);
  useEffect(() => {
    fetch(`${API_URL}/api/status`).then((response) => response.ok ? response.json() : null)
      .then((data) => setStatus(data)).catch(() => {});
  }, []);
  const updated=status?.last_successful_refresh;
  if (!updated) return null;
  const label = new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  }).format(new Date(updated));
  const detail=`Schedule: ${status?.last_schedule_refresh || "unavailable"}. Ratings: ${status?.last_rating_refresh || "unavailable"}. Prediction data: ${status?.prediction_data_status || "status unavailable"}.`;
  return <span className="data-freshness" title={detail}>Data updated {label} ⓘ</span>;
}
