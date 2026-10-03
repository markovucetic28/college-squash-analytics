import ScheduleBrowser from "@/components/ScheduleBrowser";
import { apiFetch } from "@/lib/api";
import type { Fixture } from "@/lib/types";

export default async function SchedulePage() {
  const data = await apiFetch<{ total: number; items: Fixture[] }>("/api/schedule?limit=500");
  return <>
    <p className="eyebrow">2026–27 varsity season</p>
    <h1>College squash schedule</h1>
    <p className="lede">Browse all {data.total} validated fixtures. Open any matchup for projected positions, player ratings, and team context.</p>
    <ScheduleBrowser fixtures={data.items} />
  </>;
}
