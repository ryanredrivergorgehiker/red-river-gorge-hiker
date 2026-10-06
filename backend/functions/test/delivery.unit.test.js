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
    "b8986ad11ff0107032f10c28e509579b89e0af74f2abbd2476bd6dab51eeb765",
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
