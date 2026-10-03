"use client";

import { useEffect, useMemo, useState } from "react";
import { API_URL } from "@/lib/api";
import type { Projection, Team } from "@/lib/types";
import LineupScenario from "./LineupScenario";
import StatStrip from "./StatStrip";
import { number, percent, record } from "@/lib/api";
import Link from "next/link";
import EloLabel from "./EloLabel";

type Comparison = { team_one:{program_id:number;name:string;elo:number;strength_of_schedule:number;previous_season:any}; team_two:{program_id:number;name:string;elo:number;strength_of_schedule:number;previous_season:any}; projection:Projection; historical_meetings:any[] };

export default function CompareBrowser({ teams }: { teams:Team[] }) {
  const [gender,setGender]=useState<"men"|"women">("men");
  const options=useMemo(()=>teams.filter((team)=>team.gender===gender),[teams,gender]);
  const [first,setFirst]=useState(0),[second,setSecond]=useState(0);
  const [data,setData]=useState<Comparison|null>(null);
  const [error,setError]=useState(false);
  useEffect(()=>{ if(options.length){setFirst(options[0].program_id);setSecond(options[1].program_id);} },[options]);
  useEffect(()=>{ if(!first||!second||first===second)return; const controller=new AbortController(); setError(false); fetch(`${API_URL}/api/compare?team_one_id=${first}&team_two_id=${second}`,{signal:controller.signal}).then((response)=>{if(!response.ok)throw new Error("Comparison unavailable");return response.json();}).then((result)=>{setData(result);setError(false);}).catch((reason)=>{if(reason.name!=="AbortError"){setData(null);setError(true);}}); return()=>controller.abort(); },[first,second]);
  return <>
    <div className="filters"><label>Division<select value={gender} onChange={(event)=>setGender(event.target.value as "men"|"women")}><option value="men">Men</option><option value="women">Women</option></select></label><label>Team A<select value={first} onChange={(event)=>setFirst(Number(event.target.value))}>{options.map((team)=><option key={team.program_id} value={team.program_id}>{team.name}</option>)}</select></label><label>Team B<select value={second} onChange={(event)=>setSecond(Number(event.target.value))}>{options.map((team)=><option key={team.program_id} value={team.program_id}>{team.name}</option>)}</select></label></div>
    {first===second && <section className="notice">Choose two different teams.</section>}
    {error && <section className="notice"><strong>Comparison temporarily unavailable.</strong><p>Please try again in a moment.</p></section>}
    {data && first!==second && <><LineupScenario projection={data.projection} teamOne={data.team_one.name} teamTwo={data.team_two.name} teamOneId={data.team_one.program_id} teamTwoId={data.team_two.program_id}/><h2>Team context</h2><div className="two-column">{[data.team_one,data.team_two].map((team)=><section key={team.name}><h3><Link href={`/team/${team.program_id}`}>{team.name}</Link></h3><StatStrip items={[{label:"2025–26 record",value:record(team.previous_season)},{label:<EloLabel/>,value:number(team.elo,0)},{label:"Schedule strength",value:percent(team.strength_of_schedule)},{label:"Average margin",value:team.previous_season?number(team.previous_season.average_margin):"—"}]}/></section>)}</div><p className="muted">{data.historical_meetings.length} verified historical meetings in project coverage.</p></>}
  </>;
}
