import assert from "node:assert/strict";
import test from "node:test";
import { probabilitySegments, teamColor } from "./teamColors.ts";

test("known teams have stable colors and unknown teams use the fallback", () => {
  assert.equal(teamColor("Harvard University"), "#a51c30");
  assert.equal(teamColor("Unknown College"), "#526675");
});

test("probability segments are complementary and bounded", () => {
  assert.deepEqual(probabilitySegments(.64), {left:"64%", right:"36%"});
  assert.deepEqual(probabilitySegments(.50), {left:"50%", right:"50%"});
  assert.deepEqual(probabilitySegments(.30), {left:"30%", right:"70%"});
  assert.deepEqual(probabilitySegments(.968), {left:"96.8%", right:"3.2%"});
  assert.deepEqual(probabilitySegments(2), {left:"100%", right:"0%"});
});
