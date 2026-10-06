import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_CAPABILITY_TTL_SECONDS,
  hashCapabilityToken,
  parseBearerToken,
} from "../src/delivery.js";

test("package capability TTL is frozen at five minutes", () => {
  assert.equal(DEFAULT_CAPABILITY_TTL_SECONDS, 300);
});

test("capability token is stored only by SHA-256 hash", () => {
  assert.equal(
    hashCapabilityToken("synthetic-capability-token"),
    "14344dae072018d5aaf37d59007122e38b29079b104bfd3c937bd576a6cef7e8",
  );
});

test("Bearer parser accepts exactly one opaque capability", () => {
  assert.equal(
    parseBearerToken("Bearer synthetic-capability-token"),
    "synthetic-capability-token",
  );
  assert.equal(parseBearerToken(""), null);
  assert.equal(parseBearerToken("Basic abc"), null);
  assert.equal(parseBearerToken("Bearer two tokens"), null);
});
