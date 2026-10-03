import RatingChart from "@/components/RatingChart";
import StatStrip from "@/components/StatStrip";
import { apiFetch, formatDate, number } from "@/lib/api";
import Link from "next/link";

type Player = {
  player_id:number; name:string; latest_rating:{rating:number;date:string}|null;
  current_membership:{team_name:string;gender:string;season:string;program_id?:number}|null;
  latest_membership:{team_name?:string;team?:string;gender:string;season:string;program_id?:number}|null;
  projected_position:number|null;
  verified_record:{wins:number;losses:number;matches:number}; average_position:number|null;
  memberships:{season:string;gender:string;team:string;program_id:number;roster_position?:string}[];
  matches:{date:string;season:string;position:number;opponent:string;opponent_player_id:number;opponent_team:string;opponent_team_id:number;result:string;formatted_score:string}[];
  ratings:{date:string;rating:number}[];
};

export default async function PlayerPage({ params }: { params: Promise<{ player_id:string }> }) {
  const { player_id } = await params;
  const player = await apiFetch<Player>(`/api/players/${player_id}`);
  const membership = player.current_membership;
  const latest = player.latest_membership;
  const teamName = latest?.team_name || latest?.team;
  const division = latest?.gender === "men" ? "Men’s Varsity" : latest?.gender === "women" ? "Women’s Varsity" : "Varsity division unavailable";
  return <>
    <h1>{player.name}</h1>
    <p className="player-context">{teamName && latest?.program_id ? <Link href={`/team/${latest.program_id}`}>{teamName}</Link> : teamName || "Latest team unavailable"} · {division}</p>
    <p className="roster-status">{membership ? `Official ${membership.season} roster${player.projected_position ? ` · projected position ${player.projected_position}` : " · reserve / projected order uncertain"}` : `Latest verified roster: ${latest?.season || "unavailable"}`}</p>
    <StatStrip items={[
      {label:"Latest rating",value:player.latest_rating ? number(player.latest_rating.rating,2) : "—"},
      {label:"Rating date",value:player.latest_rating?.date || "—"},
      {label:"Verified record",value:`${player.verified_record.wins}–${player.verified_record.losses}`},
      {label:"Verified matches",value:String(player.verified_record.matches)},
      {label:"Average position",value:number(player.average_position)},
    ]}/>
    {player.verified_record.matches === 0 && <section className="notice"><strong>Current-roster newcomer</strong><p>No verified college individual matches are available yet.</p></section>}
    <h2>Official rating history</h2><RatingChart ratings={player.ratings}/>
    <div className="section-bar"><h2>Recent individual matches</h2><span>{player.verified_record.matches} verified total</span></div>
    {player.matches.length ? <div className="table-wrap"><table><thead><tr><th>Date</th><th>Season</th><th>Position</th><th>Opponent</th><th>Opponent team</th><th>Result</th><th>Game scores</th></tr></thead><tbody>{player.matches.map((match,index) => <tr key={`${match.date}-${index}`}><td>{formatDate(match.date)}</td><td>{match.season}</td><td>{match.position}</td><td><Link href={`/player/${match.opponent_player_id}`}>{match.opponent}</Link></td><td><Link href={`/team/${match.opponent_team_id}`}>{match.opponent_team}</Link></td><td>{match.result}</td><td>{match.formatted_score}</td></tr>)}</tbody></table></div> : <p className="muted">No verified individual match results in current project coverage.</p>}
    <h2>Roster history</h2>
    {player.memberships.length ? <div className="table-wrap"><table><thead><tr><th>Season</th><th>Team</th><th>Division</th><th>Roster position</th></tr></thead><tbody>{player.memberships.map((item,index)=><tr key={`${item.season}-${index}`}><td>{item.season}</td><td><Link href={`/team/${item.program_id}`}>{item.team}</Link></td><td>{item.gender === "men" ? "Men" : "Women"}</td><td>{item.roster_position||"—"}</td></tr>)}</tbody></table></div> : <p className="muted">This player is on a current official roster but has no historical roster entry in the verified seasons.</p>}
    <p className="projection-note">Records and ratings reflect verified source coverage in this project and may not represent the player’s complete career.</p>
  </>;
}
