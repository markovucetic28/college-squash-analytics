import Link from "next/link";
import LineupScenario from "@/components/LineupScenario";
import StatStrip from "@/components/StatStrip";
import EloLabel from "@/components/EloLabel";
import { apiFetch, formatDate, number, percent, record } from "@/lib/api";
import type { Projection, Summary } from "@/lib/types";

type Context = { previous_season: Summary | null; historical_record: Summary | null; strength_of_schedule: number | null; elo: number };
type Match = {
  source_match_id: number; team_one: string; team_two: string; gender: string;
  team_one_id?: number; team_two_id?: number;
  match_date: string; match_time?: string; venue_name?: string; projection: Projection;
  team_one_context: Context; team_two_context: Context;
  historical_meetings: { date: string; season: string; team_score: number; opponent_score: number; result: string }[];
};

export default async function MatchPage({ params }: { params: Promise<{ match_id: string }> }) {
  const { match_id } = await params;
  const match = await apiFetch<Match>(`/api/matches/${match_id}`);
  const contexts = [match.team_one_context, match.team_two_context];
  return <>
    <p className="eyebrow">{match.gender} · upcoming fixture</p>
    <h1>{match.team_one_id ? <Link href={`/team/${match.team_one_id}`}>{match.team_one}</Link> : match.team_one} <span className="muted">at</span> {match.team_two_id ? <Link href={`/team/${match.team_two_id}`}>{match.team_two}</Link> : match.team_two}</h1>
    <p className="lede">{formatDate(match.match_date)}{match.match_time ? ` · ${match.match_time}` : ""} · {match.venue_name || "Location TBD"}</p>
    <LineupScenario projection={match.projection} teamOne={match.team_one} teamTwo={match.team_two} teamOneId={match.team_one_id} teamTwoId={match.team_two_id} />
    <h2>Team context</h2>
    <div className="two-column">{[match.team_one, match.team_two].map((team, index) => <section key={team}>
      <h3>{team}</h3><StatStrip items={[
        { label: "2025–26 record", value: record(contexts[index].previous_season) },
        { label: <EloLabel/>, value: number(contexts[index].elo, 0) },
        { label: "Schedule strength", value: percent(contexts[index].strength_of_schedule) },
        { label: "Average margin", value: contexts[index].previous_season ? number(contexts[index].previous_season!.average_margin) : "—" },
      ]} />
    </section>)}</div>
    <div className="section-bar"><h2>Prior meetings</h2><span>{match.historical_meetings.length} verified</span></div>
    {match.historical_meetings.length ? <div className="table-wrap"><table><thead><tr><th>Date</th><th>Season</th><th>Result for {match.team_one}</th><th>Score</th></tr></thead><tbody>
      {match.historical_meetings.map((meeting) => <tr key={`${meeting.date}-${meeting.season}`}><td>{formatDate(meeting.date)}</td><td>{meeting.season}</td><td>{meeting.result}</td><td>{meeting.team_score}–{meeting.opponent_score}</td></tr>)}
    </tbody></table></div> : <p className="muted">No verified meetings in the available coverage.</p>}
    <p className="projection-note"><Link href="/methodology">How these estimates are calculated →</Link></p>
  </>;
}
