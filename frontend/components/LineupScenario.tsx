"use client";

import { useEffect, useMemo, useState } from "react";
import { API_URL, displayProbability, number } from "@/lib/api";
import { lineupChanged, moveLineupPlayer, removeLineupPlayer, replaceLineupPlayer, type LineupSlot } from "@/lib/lineup";
import type { Pairing, Projection } from "@/lib/types";
import ProjectionView from "./ProjectionView";

type RosterPlayer = { player_id:number; display_name:string; current_rating:number|null };
type TeamRoster = { roster:RosterPlayer[] };

const idsFromProjection = (pairings:Pairing[], side:"one"|"two") => pairings.map((pairing) =>
  side === "one" ? pairing.team_one_player_id : pairing.team_two_player_id
);

function LineupColumn({ name, slots, roster, onChange }: {
  name:string; slots:LineupSlot[]; roster:RosterPlayer[]; onChange:(slots:LineupSlot[])=>void;
}) {
  const [dragged,setDragged]=useState<number|null>(null);
  const used=new Set(slots.filter((player):player is number=>player!=null));
  const byId=new Map(roster.map((player)=>[player.player_id,player]));
  const activeCount=used.size;
  return <section className="lineup-column">
    <h3>{name}</h3>
    <ol className="lineup-editor-list">
      {slots.map((playerId,index)=>{
        const player=playerId==null?null:byId.get(playerId);
        return <li key={`${index}-${playerId ?? "forfeit"}`} onDragOver={(event)=>event.preventDefault()} onDrop={()=>{
          if(dragged!=null && index<activeCount) onChange(moveLineupPlayer(slots,dragged,index));
          setDragged(null);
        }}>
          <span className="position">{index+1}</span>
          {player ? <>
            <button className="drag-handle" draggable aria-label={`Move ${player.display_name}`} title="Drag to reorder" onDragStart={()=>setDragged(index)}>↕</button>
            <span className="lineup-player"><strong>{player.display_name}</strong><small>{number(player.current_rating,2)}</small></span>
            <span className="lineup-move-buttons"><button disabled={index===0} onClick={()=>onChange(moveLineupPlayer(slots,index,index-1))} aria-label={`Move ${player.display_name} up`}>↑</button><button disabled={index>=activeCount-1} onClick={()=>onChange(moveLineupPlayer(slots,index,index+1))} aria-label={`Move ${player.display_name} down`}>↓</button></span>
            <select aria-label={`Replace ${player.display_name}`} value="" onChange={(event)=>event.target.value && onChange(replaceLineupPlayer(slots,index,Number(event.target.value)))}>
              <option value="">Replace player…</option>
              {roster.filter((candidate)=>!used.has(candidate.player_id)).map((candidate)=><option key={candidate.player_id} value={candidate.player_id}>{candidate.display_name} · {number(candidate.current_rating,2)}</option>)}
            </select>
            <button className="text-button" onClick={()=>onChange(removeLineupPlayer(slots,index))}>Unavailable</button>
          </> : <><strong className="forfeit-label">Forfeit</strong><select aria-label={`Fill position ${index+1}`} value="" onChange={(event)=>event.target.value && onChange(replaceLineupPlayer(slots,index,Number(event.target.value)))}><option value="">Add roster player…</option>{roster.filter((candidate)=>!used.has(candidate.player_id)).map((candidate)=><option key={candidate.player_id} value={candidate.player_id}>{candidate.display_name} · {number(candidate.current_rating,2)}</option>)}</select></>}
        </li>;
      })}
    </ol>
  </section>;
}

export default function LineupScenario({ projection, teamOne, teamTwo, teamOneId, teamTwoId }: {
  projection:Projection; teamOne:string; teamTwo:string; teamOneId?:number; teamTwoId?:number;
}) {
  const canEdit=Boolean(projection.available && projection.pairings && teamOneId && teamTwoId);
  const originals=useMemo(()=>projection.pairings ? {
    one:idsFromProjection(projection.pairings,"one"), two:idsFromProjection(projection.pairings,"two")
  } : {one:[],two:[]},[projection]);
  const [editing,setEditing]=useState(false);
  const [one,setOne]=useState<LineupSlot[]>(originals.one);
  const [two,setTwo]=useState<LineupSlot[]>(originals.two);
  const [rosters,setRosters]=useState<{one:RosterPlayer[];two:RosterPlayer[]}|null>(null);
  const [custom,setCustom]=useState<Projection|null>(null);
  const [error,setError]=useState<string|null>(null);
  const changed=lineupChanged(originals.one,one)||lineupChanged(originals.two,two);

  useEffect(()=>{ setEditing(false); setOne(originals.one); setTwo(originals.two); setCustom(null); setError(null); },[originals]);
  useEffect(()=>{
    if(!editing||!teamOneId||!teamTwoId||rosters) return;
    Promise.all([
      fetch(`${API_URL}/api/teams/${teamOneId}`).then((response)=>response.json() as Promise<TeamRoster>),
      fetch(`${API_URL}/api/teams/${teamTwoId}`).then((response)=>response.json() as Promise<TeamRoster>),
    ]).then(([first,second])=>setRosters({one:first.roster,two:second.roster})).catch(()=>setError("Could not load the current official rosters."));
  },[editing,teamOneId,teamTwoId,rosters]);
  useEffect(()=>{
    if(!editing||!teamOneId||!teamTwoId) return;
    if(one.filter((player)=>player!=null).length<7||two.filter((player)=>player!=null).length<7){
      setCustom(null);setError("A what-if lineup needs at least seven eligible players.");return;
    }
    const controller=new AbortController();
    const timer=setTimeout(()=>fetch(`${API_URL}/api/compare/custom-lineup`,{
      method:"POST",headers:{"Content-Type":"application/json"},signal:controller.signal,
      body:JSON.stringify({team_one_id:teamOneId,team_two_id:teamTwoId,team_one_lineup:one,team_two_lineup:two}),
    }).then(async(response)=>{
      if(!response.ok){const payload=await response.json();throw new Error(payload.detail||"Invalid custom lineup");}
      return response.json();
    }).then((result)=>{setCustom(result);setError(null);}).catch((reason)=>{
      if(reason.name!=="AbortError"){setCustom(null);setError(reason.message);}
    }),150);
    return()=>{clearTimeout(timer);controller.abort();};
  },[editing,one,two,teamOneId,teamTwoId]);

  const shown=editing&&custom?custom:projection;
  const reset=()=>{setOne(originals.one);setTwo(originals.two);setCustom(null);setEditing(false);setError(null);};
  return <>
    <div className="scenario-actions">
      {!editing ? <button disabled={!canEdit} onClick={()=>setEditing(true)}>Edit lineup</button> : <><span className="badge accent">Custom scenario</span><button onClick={reset}>Reset lineup</button><button onClick={()=>setEditing(false)}>Close editor</button></>}
    </div>
    {editing&&<section className="lineup-scenario"><div className="section-bar"><h2>What-if lineup scenario</h2><span>Scenario only — changes are not saved</span></div><p className="projection-note">This lineup was edited by you and is not an official or projected lineup. Reordering does not certify CSA lineup-order legality. Use the arrow buttons as a keyboard-accessible alternative to dragging.</p>{rosters?<div className="two-column"><LineupColumn name={teamOne} slots={one} roster={rosters.one} onChange={setOne}/><LineupColumn name={teamTwo} slots={two} roster={rosters.two} onChange={setTwo}/></div>:<p>Loading official rosters…</p>}{error&&<p className="form-error" role="alert">{error}</p>}</section>}
    {editing&&custom&&changed&&<p className="scenario-change"><strong>Original projection:</strong> {teamOne} {displayProbability(projection.team_one_probability)} · <strong>Custom lineup:</strong> {teamOne} {displayProbability(custom.team_one_probability)} · <strong>Change:</strong> {custom.team_one_probability!=null&&projection.team_one_probability!=null?`${custom.team_one_probability>=projection.team_one_probability?"+":""}${((custom.team_one_probability-projection.team_one_probability)*100).toFixed(1)} percentage points`:"—"}<br/><span>Expected wins: {number(projection.team_one_expected_wins)} → {number(custom.team_one_expected_wins)}</span></p>}
    <ProjectionView projection={shown} teamOne={teamOne} teamTwo={teamTwo}/>
  </>;
}
