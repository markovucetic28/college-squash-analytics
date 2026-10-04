import assert from "node:assert/strict";
import test from "node:test";
import { probabilityAdvantage, probabilitySegments, teamColor } from "./teamColors.ts";

test("known teams have stable colors and unknown teams use the fallback", () => {
  assert.equal(teamColor("Harvard University"), "#a51c30");
  assert.equal(teamColor("Unknown College"), "#526675");
});

test("directional advantage starts at the fixed center and points to the favorite",()=>{
  assert.deepEqual(probabilityAdvantage(.70),{side:"left",width:"40%"});
  assert.deepEqual(probabilityAdvantage(.30),{side:"right",width:"40%"});
  assert.deepEqual(probabilityAdvantage(.50),{side:"left",width:"0%"});
});

test("probability segments are complementary and bounded", () => {
  assert.deepEqual(probabilitySegments(.64), {left:"64%", right:"36%"});
  assert.deepEqual(probabilitySegments(2), {left:"100%", right:"0%"});
});
