import Link from "next/link";
import { apiFetch } from "@/lib/api";
import RankingControls from "@/components/RankingControls";
import RankingsTable, { type Ranking } from "@/components/RankingsTable";

const seasons = ["2026-27","2025-26","2024-25","2023-24","2022-23","2021-22","2019-20"];

export default async function RankingsPage({ searchParams }: { searchParams:Promise<{gender?:string;season?:string}> }) {
  const query = await searchParams;
  const gender = query.gender === "women" ? "women" : "men";
  const season = seasons.includes(query.season || "") ? query.season! : "2025-26";
  const data = await apiFetch<{items:Ranking[]}>(`/api/rankings?gender=${gender}&season=${season}`);
  return <>
    <p className="eyebrow">Descriptive, not official CSA rankings</p><h1>Project rankings</h1>
    <p className="lede">Ordered by win percentage, schedule strength, and average scoring margin. Elo is shown separately.</p>
    <div className="tabs"><Link className={gender==="men"?"active":""} href={`/rankings?gender=men&season=${season}`}>Men</Link><Link className={gender==="women"?"active":""} href={`/rankings?gender=women&season=${season}`}>Women</Link></div>
    <RankingControls gender={gender} season={season} seasons={seasons}/>
    <RankingsTable rows={data.items}/>
  </>;
}
