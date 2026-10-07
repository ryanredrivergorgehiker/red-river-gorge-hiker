import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_CAPABILITY_TTL_SECONDS,
  DIRECT_READ_TTL_SECONDS,
  createSignedPackageReadUrl,
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


test("direct signed read is object-scoped and bounded to one minute", async () => {
  let options = null;
  const file = {
    async getSignedUrl(value) {
      options = value;
      return ["https://storage.googleapis.com/example/signed-object?X-Goog-Signature=test"];
    },
  };

  const nowMs = Date.parse("2026-10-07T22:00:00Z");
  const capabilityExpiresAt = {
    toMillis() {
      return nowMs + 5 * 60 * 1000;
    },
  };

  const result = await createSignedPackageReadUrl(
    file,
    capabilityExpiresAt,
    nowMs,
  );

  assert.equal(DIRECT_READ_TTL_SECONDS, 60);
  assert.equal(options.version, "v4");
  assert.equal(options.action, "read");
  assert.equal(
    options.expires.getTime(),
    nowMs + 60_000,
  );
  assert.equal(
    result.expiresAtMs,
    nowMs + 60_000,
  );
  assert.match(result.url, /^https:\/\//);
});

test("direct signed read can never outlive the Bearer capability", async () => {
  let expires = null;
  const file = {
    async getSignedUrl(options) {
      expires = options.expires.getTime();
      return ["https://storage.googleapis.com/example/signed-object?X-Goog-Signature=test"];
    },
  };

  const nowMs = Date.parse("2026-10-07T22:00:00Z");
  await createSignedPackageReadUrl(
    file,
    {
      toMillis() {
        return nowMs + 12_000;
      },
    },
    nowMs,
  );

  assert.equal(expires, nowMs + 12_000);
});
