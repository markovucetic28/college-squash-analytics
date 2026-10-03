import assert from "node:assert/strict";
import test from "node:test";

import { sortRankings, type Ranking } from "./rankings.ts";

const rows:Ranking[]=[
  {rank:1,program_id:1,team:"Alpha",wins:9,losses:10,win_percentage:9/19,elo:1510,strength_of_schedule:.55,average_margin:1,recent_form:""},
  {rank:2,program_id:2,team:"Beta",wins:10,losses:2,win_percentage:10/12,elo:1600,strength_of_schedule:.48,average_margin:3,recent_form:""},
];

test("record sorting uses win percentage rather than record text",()=>{
  assert.equal(sortRankings(rows,"record","desc")[0].team,"Beta");
  assert.equal(sortRankings(rows,"record","asc")[0].team,"Alpha");
});

test("metric sorting supports Elo and schedule strength",()=>{
  assert.equal(sortRankings(rows,"elo","desc")[0].team,"Beta");
  assert.equal(sortRankings(rows,"strength_of_schedule","desc")[0].team,"Alpha");
});
