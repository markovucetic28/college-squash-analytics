import Link from "next/link";
import StatStrip from "@/components/StatStrip";
import EloLabel from "@/components/EloLabel";
import { apiFetch, formatDate, number, percent, record } from "@/lib/api";
import type { Fixture, Summary } from "@/lib/types";

type RosterPlayer = { player_id:number; display_name:string; current_rating:number; rating_date:string; projected_position?:number; career_wins:number; career_matches:number };
type TeamDetail = {
  program_id:number; name:string; gender:string; season:string; elo:number; strength_of_schedule:number|null;
  current_season:(Summary & {elo:number;strength_of_schedule:number})|null; previous_season:Summary|null; historical_record:Summary|null; lineup_confidence:number;
  roster:RosterPlayer[]; schedule:Fixture[];
  previous_results:{ source_match_id:number; date:string; opponent:string; result:string; team_score:number; opponent_score:number }[];
  season_history:{season:string;wins:number;losses:number;win_percentage:number;average_margin:number;strength_of_schedule:number}[];
};

export default async function TeamPage({ params }: { params: Promise<{ team_id: string }> }) {
  const { team_id } = await params;
  const team = await apiFetch<TeamDetail>(`/api/teams/${team_id}`);
  return <>
    <p className="eyebrow">{team.gender} · {team.season}</p><h1>{team.name}</h1>
    <StatStrip items={[
      {label:"2026–27 record",value:record(team.current_season)}, {label:<EloLabel/>,value:number(team.current_season?.elo ?? team.elo,0)},
      {label:"Schedule strength",value:percent(team.current_season?.strength_of_schedule)},
      {label:"Average margin",value:team.current_season ? number(team.current_season.average_margin) : "—"},
      {label:"Historical record",value:record(team.historical_record)},
    ]}/>
    <div className="section-bar"><h2>Current official roster</h2><span>Projected order confidence {percent(team.lineup_confidence,0)}</span></div>
    <div className="table-wrap"><table><thead><tr><th>Projected pos.</th><th>Player</th><th>Latest rating</th><th>Rating date</th><th>Verified college record</th></tr></thead><tbody>
      {team.roster.map((player) => <tr key={player.player_id}><td>{player.projected_position || "—"}</td><td><Link href={`/player/${player.player_id}`}>{player.display_name}</Link></td><td>{number(player.current_rating,2)}</td><td>{player.rating_date}</td><td>{player.career_wins}–{player.career_matches-player.career_wins}</td></tr>)}
    </tbody></table></div>
    <div className="section-bar"><h2>2026–27 schedule</h2><span>{team.schedule.length} fixtures</span></div>
    <div className="table-wrap"><table><thead><tr><th>Date</th><th>Opponent</th><th>Location</th><th>Status</th></tr></thead><tbody>{team.schedule.map((match) => <tr key={match.source_match_id}><td><Link href={`/match/${match.source_match_id}`}>{formatDate(match.match_date)}</Link></td><td>{match.home_team===team.name ? match.away_team : match.home_team}</td><td>{match.venue_name||"TBD"}</td><td>{match.status}</td></tr>)}</tbody></table></div>
    <h2>Previous verified results</h2>
    <div className="table-wrap"><table><thead><tr><th>Date</th><th>Opponent</th><th>Result</th><th>Score</th></tr></thead><tbody>{team.previous_results.map((match) => <tr key={match.source_match_id}><td>{formatDate(match.date)}</td><td>{match.opponent}</td><td>{match.result}</td><td>{match.team_score}–{match.opponent_score}</td></tr>)}</tbody></table></div>
    <h2>Season-by-season history</h2>
    <div className="table-wrap"><table><thead><tr><th>Season</th><th>Record</th><th>Win %</th><th>Margin</th><th>SOS</th></tr></thead><tbody>{team.season_history.map((season) => <tr key={season.season}><td>{season.season}</td><td>{season.wins}–{season.losses}</td><td>{percent(season.win_percentage)}</td><td>{number(season.average_margin)}</td><td>{percent(season.strength_of_schedule)}</td></tr>)}</tbody></table></div>
  </>;
}
