import assert from "node:assert/strict";
import test from "node:test";
import { formatRatingAxisDate, formatRatingTooltipDate } from "./chart.ts";

test("rating chart dates distinguish year ticks from exact tooltip dates", () => {
  assert.equal(formatRatingAxisDate("2015-03-15"), "Mar ’15");
  assert.equal(formatRatingTooltipDate("2015-03-15"), "Mar 15, 2015");
});
