import assert from "node:assert/strict";
import test from "node:test";

import { displayProbability, number, resolveApiUrl } from "./api.ts";

test("future probability formatting bounds display values only", () => {
  const rawLow = 0.000004;
  const rawHigh = 0.999999;

  assert.equal(displayProbability(rawLow), "0.1%");
  assert.equal(displayProbability(rawHigh), "99.9%");
  assert.equal(displayProbability(0.5), "50.0%");
  assert.equal(rawLow, 0.000004);
  assert.equal(rawHigh, 0.999999);
});

test("production API base URL takes precedence over the legacy setting", () => {
  assert.equal(resolveApiUrl({
    NEXT_PUBLIC_API_BASE_URL: "https://api.example.org",
    NEXT_PUBLIC_API_URL: "http://legacy",
  }), "https://api.example.org");
});

test("production configuration cannot silently fall back to localhost", () => {
  assert.throws(() => resolveApiUrl({ NODE_ENV: "production" }), /NEXT_PUBLIC_API_BASE_URL/);
  assert.equal(resolveApiUrl({ NODE_ENV: "development" }), "http://127.0.0.1:8000");
});

test("continuous metrics default to hundredths while integer metrics can opt out", () => {
  assert.equal(number(6.1), "6.10");
  assert.equal(number(7.2), "7.20");
  assert.equal(number(1836.4, 0), "1836");
});
