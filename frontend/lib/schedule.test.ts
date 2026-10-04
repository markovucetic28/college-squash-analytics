import assert from "node:assert/strict";
import test from "node:test";
import { estimateState } from "./schedule.ts";

test("schedule distinguishes loading from a completed unavailable estimate",()=>{
  assert.equal(estimateState(true,false,false,false),"loading");
  assert.equal(estimateState(true,false,false,true),"loading");
  assert.equal(estimateState(true,true,false,false),"unavailable");
  assert.equal(estimateState(true,true,true,false),"available");
  assert.equal(estimateState(false,false,false,false),"team_only");
});
