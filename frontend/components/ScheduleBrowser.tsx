"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_URL, displayProbability, formatDate } from "@/lib/api";
import type { Fixture } from "@/lib/types";
import { estimateState } from "@/lib/schedule";

type ScheduleEstimate = {match_id:number;available:boolean;error?:boolean;team_one_probability?:number;team_two_probability?:number;mode_label?:string};

function DateGroup({date,matches,nextMatches,estimates,loading,load}:{date:string;matches:Fixture[];nextMatches:Fixture[];estimates:Map<number,ScheduleEstimate>;loading:Set<number>;load:(ids:number[])=>void}) {
  const section=useRef<HTMLElement>(null);
  useEffect(()=>{ if(!section.current)return; const observer=new IntersectionObserver(([entry])=>{if(entry.isIntersecting)load([...matches,...nextMatches].map((match)=>match.source_match_id));},{rootMargin:"500px"});observer.observe(section.current);return()=>observer.disconnect();},[matches,nextMatches,load]);
  const today=new Date().toLocaleDateString("en-CA",{timeZone:"America/New_York"});
  return <section className="date-group" ref={section}><h3>{date===today?`Today · ${formatDate(date)}`:formatDate(date)}</h3>{matches.map((match)=>{
    const estimate=estimates.get(match.source_match_id);
    const scheduled=match.status.toLowerCase()==="scheduled";
    const estimateStatus=estimateState(Boolean(match.projection_available),Boolean(estimate),Boolean(estimate?.available),loading.has(match.source_match_id));
    return <Link className="fixture-row" href={`/match/${match.source_match_id}`} key={match.source_match_id}>
      <div className="meta">{match.match_time||"Time TBD"}</div>
      <div className="teams"><span>{match.away_team}{scheduled&&estimate?.available&&<b>{displayProbability(estimate.team_one_probability)}</b>}</span><span>{match.home_team}{scheduled&&estimate?.available&&<b>{displayProbability(estimate.team_two_probability)}</b>}</span></div>
      <div><span className="badge">{match.gender}</span></div><div className="venue">{match.venue_name||"Location TBD"}</div>
      <div>{!scheduled?<span className="badge">Completed</span>:estimateStatus==="team_only"?<span className="badge">Team only</span>:estimateStatus==="loading"?<span className="schedule-loading">Loading estimate…</span>:estimate?.error?<span className="form-error">Estimate failed</span>:estimateStatus==="unavailable"?<span className="muted">Estimate unavailable</span>:<span className="badge accent">{estimate?.mode_label||"Projection"}</span>}</div>
    </Link>;
  })}</section>;
}

export default function ScheduleBrowser({fixtures}:{fixtures:Fixture[]}) {
  const [gender,setGender]=useState("all"),[team,setTeam]=useState("all"),[status,setStatus]=useState("upcoming"),[start,setStart]=useState(""),[end,setEnd]=useState("");
  const [estimates,setEstimates]=useState(new Map<number,ScheduleEstimate>()),[loading,setLoading]=useState(new Set<number>());
  const pending=useRef(new Set<number>());
  const teams=useMemo(()=>Array.from(new Set(fixtures.flatMap((match)=>[match.home_team,match.away_team]))).sort(),[fixtures]);
  const filtered=fixtures.filter((match)=>(gender==="all"||match.gender===gender)&&(team==="all"||match.home_team===team||match.away_team===team)&&(status==="all"||(status==="upcoming"&&match.status.toLowerCase()==="scheduled")||(status==="completed"&&match.status.toLowerCase()!=="scheduled"))&&(!start||match.match_date>=start)&&(!end||match.match_date<=end));
  const groups=[...Map.groupBy(filtered,(match)=>match.match_date).entries()];
  const load=useCallback((ids:number[])=>{
    const needed=ids.filter((id)=>!estimates.has(id)&&!pending.current.has(id)).slice(0,40); if(!needed.length)return;
    needed.forEach((id)=>pending.current.add(id)); setLoading((previous)=>new Set([...previous,...needed]));
    fetch(`${API_URL}/api/schedule/predictions`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({match_ids:needed})}).then(async(response)=>{if(!response.ok)throw new Error("Schedule estimates unavailable");return response.json();}).then((payload:{items:ScheduleEstimate[]})=>setEstimates((previous)=>{const next=new Map(previous);payload.items.forEach((item)=>next.set(item.match_id,item));needed.filter((id)=>!next.has(id)).forEach((id)=>next.set(id,{match_id:id,available:false}));return next;})).catch(()=>setEstimates((previous)=>{const next=new Map(previous);needed.forEach((id)=>next.set(id,{match_id:id,available:false,error:true}));return next;})).finally(()=>{needed.forEach((id)=>pending.current.delete(id));setLoading((previous)=>{const next=new Set(previous);needed.forEach((id)=>next.delete(id));return next;});});
  },[estimates]);
  useEffect(()=>{load(groups.slice(0,2).flatMap(([,matches])=>matches.map((match)=>match.source_match_id)));},[gender,team,status,start,end]); // eslint-disable-line react-hooks/exhaustive-deps
  return <><div className="filters"><label>Division<select value={gender} onChange={(event)=>setGender(event.target.value)}><option value="all">Men & Women</option><option value="men">Men</option><option value="women">Women</option></select></label><label>Team<select value={team} onChange={(event)=>setTeam(event.target.value)}><option value="all">All teams</option>{teams.map((name)=><option key={name}>{name}</option>)}</select></label><label>Status<select value={status} onChange={(event)=>setStatus(event.target.value)}><option value="upcoming">Upcoming</option><option value="completed">Completed</option><option value="all">All</option></select></label><label>From<input type="date" value={start} onChange={(event)=>setStart(event.target.value)}/></label><label>Through<input type="date" value={end} onChange={(event)=>setEnd(event.target.value)}/></label></div><div className="section-bar"><h2>Season fixtures</h2><span>{filtered.length} matches</span></div>{!filtered.length&&<p className="muted">No fixtures match these filters.</p>}{groups.map(([date,matches],index)=><DateGroup key={date} date={date} matches={matches} nextMatches={groups[index+1]?.[1]||[]} estimates={estimates} loading={loading} load={load}/>)}</>;
}
