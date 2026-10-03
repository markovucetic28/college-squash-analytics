import assert from "node:assert/strict";
import test from "node:test";
import { lineupChanged, moveLineupPlayer, normalizeLineup, removeLineupPlayer, replaceLineupPlayer } from "./lineup.ts";

const original = [1,2,3,4,5,6,7,8,9];

test("drag reorder shifts intervening players", () => {
  assert.deepEqual(moveLineupPlayer(original, 3, 1), [1,4,2,3,5,6,7,8,9]);
});

test("replacement rejects duplicates and reset state is detectable", () => {
  assert.throws(() => replaceLineupPlayer(original, 0, 2));
  const changed = replaceLineupPlayer(original, 0, 10);
  assert.equal(lineupChanged(original, changed), true);
  assert.equal(lineupChanged(original, [...original]), false);
});

test("removal compacts players and leaves bottom forfeits", () => {
  assert.deepEqual(removeLineupPlayer(original, 3), [1,2,3,5,6,7,8,9,null]);
  assert.deepEqual(normalizeLineup([1,2,3,4,5,6,7,null,null]), [1,2,3,4,5,6,7,null,null]);
});
