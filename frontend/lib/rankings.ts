export type Ranking = {rank:number;program_id:number;team:string;wins:number;losses:number;win_percentage:number;elo:number;strength_of_schedule:number;average_margin:number;recent_form:string};
export type RankingSortKey="rank"|"record"|"elo"|"win_percentage"|"strength_of_schedule"|"average_margin";

export function sortRankings(rows:Ranking[],key:RankingSortKey,direction:"asc"|"desc"){
  return [...rows].sort((a,b)=>{
    let difference=0;
    if(key==="record") difference=a.win_percentage-b.win_percentage||a.wins-b.wins||b.losses-a.losses;
    else difference=a[key]-b[key];
    if(!difference) difference=a.team.localeCompare(b.team);
    return direction==="asc"?difference:-difference;
  });
}
