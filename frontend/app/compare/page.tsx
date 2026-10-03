import CompareBrowser from "@/components/CompareBrowser";
import { apiFetch } from "@/lib/api";
import type { Team } from "@/lib/types";

export default async function ComparePage(){const teams=await apiFetch<Team[]>("/api/teams");return <><p className="eyebrow">Matchup explorer</p><h1>Compare varsity teams</h1><p className="lede">Projected individual pairings lead the comparison; team-level context and historical meetings provide supporting evidence.</p><CompareBrowser teams={teams}/></>}
