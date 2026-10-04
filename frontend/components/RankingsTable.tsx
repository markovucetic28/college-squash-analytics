"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { number, percent } from "@/lib/api";
import { sortRankings, type Ranking, type RankingSortKey as SortKey } from "@/lib/rankings";
import EloLabel from "./EloLabel";
import type { ReactNode } from "react";

export type { Ranking } from "@/lib/rankings";

export default function RankingsTable({rows}:{rows:Ranking[]}){
  const [sort,setSort]=useState<{key:SortKey;direction:"asc"|"desc"}>({key:"rank",direction:"asc"});
  const [query,setQuery]=useState("");
  const sorted=useMemo(()=>sortRankings(rows.filter((row)=>row.team.toLowerCase().includes(query.trim().toLowerCase())),sort.key,sort.direction),[rows,sort,query]);
  const change=(key:SortKey)=>setSort((current)=>({key,direction:current.key===key?(current.direction==="desc"?"asc":"desc"):(key==="rank"?"asc":"desc")}));
  const heading=(label:ReactNode,key:SortKey)=><button className="sort-heading" onClick={()=>change(key)}>{label}<span>{sort.key===key?(sort.direction==="asc"?"↑":"↓"):"↕"}</span></button>;
  return <><label className="ranking-search">Find team<input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Search rankings"/></label><div className="table-wrap"><table><thead><tr><th>{heading("Rank","rank")}</th><th>Team</th><th>{heading("Record","record")}</th><th>{heading(<EloLabel/>,"elo")}</th><th>{heading("Win %","win_percentage")}</th><th title="Mean win percentage of opponents faced.">{heading("SOS ⓘ","strength_of_schedule")}</th><th title="Average team score minus opponent score.">{heading("Margin ⓘ","average_margin")}</th><th>Recent</th></tr></thead><tbody>{sorted.map((team)=><tr key={team.program_id}><td className="position">{team.rank}</td><td><Link href={`/team/${team.program_id}`}>{team.team}</Link></td><td>{team.wins}–{team.losses}</td><td>{number(team.elo,0)}</td><td>{percent(team.win_percentage)}</td><td>{percent(team.strength_of_schedule)}</td><td>{number(team.average_margin)}</td><td>{team.recent_form}</td></tr>)}</tbody></table></div>{sorted.length===0&&<p className="muted">No ranked teams match that search.</p>}</>;
}
