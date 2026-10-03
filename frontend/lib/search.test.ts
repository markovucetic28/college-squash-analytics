import assert from "node:assert/strict";
import test from "node:test";
import { isExpectedAbort } from "./search.ts";

test("search cancellation recognizes normal AbortController cleanup", () => {
  const controller = new AbortController();
  controller.abort();
  assert.equal(isExpectedAbort(new DOMException("Aborted", "AbortError"), controller.signal), true);
  assert.equal(isExpectedAbort(new Error("Network failed"), new AbortController().signal), false);
});
