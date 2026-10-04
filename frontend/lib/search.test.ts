import assert from "node:assert/strict";
import test from "node:test";
import { isExpectedAbort, nextSearchIndex } from "./search.ts";

test("search cancellation recognizes normal AbortController cleanup", () => {
  const controller = new AbortController();
  controller.abort();
  assert.equal(isExpectedAbort(new DOMException("Aborted", "AbortError"), controller.signal), true);
  assert.equal(isExpectedAbort(new Error("Network failed"), new AbortController().signal), false);
});

test("search keyboard index wraps and supports an unopened list", () => {
  assert.equal(nextSearchIndex(-1, 1, 3), 0);
  assert.equal(nextSearchIndex(-1, -1, 3), 2);
  assert.equal(nextSearchIndex(2, 1, 3), 0);
  assert.equal(nextSearchIndex(0, -1, 3), 2);
  assert.equal(nextSearchIndex(0, 1, 0), -1);
});
