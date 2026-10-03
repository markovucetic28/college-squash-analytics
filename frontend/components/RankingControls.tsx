"use client";

import { useRouter } from "next/navigation";

export default function RankingControls({ gender, season, seasons }: {
  gender: string; season: string; seasons: string[];
}) {
  const router = useRouter();
  return <div className="filters">
    <label>Season<select value={season} onChange={(event) => router.push(`/rankings?gender=${gender}&season=${event.target.value}`)}>{seasons.map((item)=><option key={item}>{item}</option>)}</select></label>
  </div>;
}
