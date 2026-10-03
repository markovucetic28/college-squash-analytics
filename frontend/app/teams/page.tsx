import Link from "next/link";
import { apiFetch } from "@/lib/api";
import type { Team } from "@/lib/types";

export default async function TeamsPage() {
  const teams = await apiFetch<Team[]>("/api/teams");
  return <>
    <p className="eyebrow">Official 2026–27 rosters</p><h1>Varsity teams</h1>
    <p className="lede">Open a program for its current roster, schedule, verified results, and season history.</p>
    {(["men", "women"] as const).map((gender) => <section key={gender}>
      <div className="section-bar"><h2>{gender === "men" ? "Men" : "Women"}</h2><span>{teams.filter((team) => team.gender === gender).length} programs</span></div>
      <div className="team-list">{teams.filter((team) => team.gender === gender).map((team) => <Link key={team.program_id} href={`/team/${team.program_id}`}><strong>{team.name}</strong><span>View →</span></Link>)}</div>
    </section>)}
  </>;
}
