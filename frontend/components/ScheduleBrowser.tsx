"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDate } from "@/lib/api";
import type { Fixture } from "@/lib/types";
import ScheduleProbability from "./ScheduleProbability";

export default function ScheduleBrowser({ fixtures }: { fixtures: Fixture[] }) {
  const [gender, setGender] = useState("all");
  const [team, setTeam] = useState("all");
  const [status, setStatus] = useState("upcoming");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const teams = useMemo(() => Array.from(new Set(fixtures.flatMap((match) => [match.home_team, match.away_team]))).sort(), [fixtures]);
  const filtered = fixtures.filter((match) =>
    (gender === "all" || match.gender === gender) &&
    (team === "all" || match.home_team === team || match.away_team === team) &&
    (status === "all" || (status === "upcoming" && match.status.toLowerCase() === "scheduled") || (status === "completed" && match.status.toLowerCase() !== "scheduled")) &&
    (!start || match.match_date >= start) && (!end || match.match_date <= end)
  );
  const groups = Map.groupBy(filtered, (match) => match.match_date);
  const today = new Date().toLocaleDateString("en-CA", {timeZone:"America/New_York"});

  return <>
    <div className="filters">
      <label>Division<select value={gender} onChange={(event) => setGender(event.target.value)}><option value="all">Men & Women</option><option value="men">Men</option><option value="women">Women</option></select></label>
      <label>Team<select value={team} onChange={(event) => setTeam(event.target.value)}><option value="all">All teams</option>{teams.map((name) => <option key={name}>{name}</option>)}</select></label>
      <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="upcoming">Upcoming</option><option value="completed">Completed</option><option value="all">All</option></select></label>
      <label>From<input type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label>
      <label>Through<input type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
    </div>
    <div className="section-bar"><h2>Season fixtures</h2><span>{filtered.length} matches</span></div>
    {filtered.length===0&&<p className="muted">No fixtures match these filters.</p>}
    {[...groups.entries()].map(([date, matches]) => <section className="date-group" key={date}>
      <h3>{date===today?`Today · ${formatDate(date)}`:formatDate(date)}</h3>
      {matches.map((match) => <Link className="fixture-row" href={`/match/${match.source_match_id}`} key={match.source_match_id}>
        <div className="meta">{match.match_time || "Time TBD"}</div>
        <div className="teams"><span>{match.away_team}</span><span>{match.home_team}</span></div>
        <div><span className="badge">{match.gender}</span></div>
        <div className="venue">{match.venue_name || "Location TBD"}</div>
        <div>{match.status.toLowerCase()!=="scheduled" ? <span className="badge">Completed</span> : match.projection_available ? <ScheduleProbability matchId={match.source_match_id} awayTeam={match.away_team} homeTeam={match.home_team}/> : <span className="badge">Team only</span>}</div>
      </Link>)}
    </section>)}
  </>;
}
