import assert from "node:assert/strict";
import test from "node:test";
import { predictionModeExplanation } from "./presentation.ts";

test("prediction modes have compact explanations", () => {
  assert.match(predictionModeExplanation("projected"), /recent official lineup evidence/);
  assert.match(predictionModeExplanation("team_only"), /team model/);
});
