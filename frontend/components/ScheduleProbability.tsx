"use client";

import { useEffect, useRef, useState } from "react";
import { API_URL, displayProbability } from "@/lib/api";

type MatchProjection = { projection?: { team_one_probability?: number; team_two_probability?: number } };

export default function ScheduleProbability({ matchId, awayTeam, homeTeam }: {matchId:number;awayTeam:string;homeTeam:string}) {
  const root = useRef<HTMLDivElement>(null);
  const [data,setData] = useState<MatchProjection|null>(null);
  const [visible,setVisible] = useState(false);
  useEffect(() => {
    if (!root.current) return;
    const observer = new IntersectionObserver(([entry]) => entry.isIntersecting && setVisible(true), {rootMargin:"160px"});
    observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible || data) return;
    const controller = new AbortController();
    fetch(`${API_URL}/api/matches/${matchId}`, {signal:controller.signal})
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => payload && setData(payload))
      .catch((error) => { if (error.name !== "AbortError") setData({}); });
    return () => controller.abort();
  }, [visible,data,matchId]);
  const projection=data?.projection;
  return <div ref={root} className="schedule-probability" aria-label="Projected matchup probability">
    {projection?.team_one_probability != null ? <><span title={awayTeam}>{displayProbability(projection.team_one_probability)}</span><span title={homeTeam}>{displayProbability(projection.team_two_probability)}</span></> : <span className="muted">{visible ? "Estimate unavailable" : "Estimate"}</span>}
  </div>;
}
