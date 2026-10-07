import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_CAPABILITY_TTL_SECONDS,
  MAX_PROXY_RANGE_BYTES,
  hashCapabilityToken,
  parseBearerToken,
  resolveProtectedPackageRange,
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



test("small protected package can still use one exact response", () => {
  const range = resolveProtectedPackageRange(
    null,
    8_201,
  );

  assert.deepEqual(range, {
    valid: true,
    partial: false,
    start: 0,
    end: 8_200,
    length: 8_201,
  });
});

test("large protected package requires bounded byte ranges", () => {
  assert.equal(MAX_PROXY_RANGE_BYTES, 8 * 1024 * 1024);

  const noRange = resolveProtectedPackageRange(
    null,
    MAX_PROXY_RANGE_BYTES + 1,
  );
  assert.equal(noRange.valid, false);
  assert.equal(noRange.reason, "range_required");

  const first = resolveProtectedPackageRange(
    "bytes=0-8388607",
    11_000_000,
  );
  assert.deepEqual(first, {
    valid: true,
    partial: true,
    start: 0,
    end: 8_388_607,
    length: 8_388_608,
  });

  const final = resolveProtectedPackageRange(
    "bytes=8388608-10999999",
    11_000_000,
  );
  assert.deepEqual(final, {
    valid: true,
    partial: true,
    start: 8_388_608,
    end: 10_999_999,
    length: 2_611_392,
  });
});

test("range contract rejects oversized or invalid requests", () => {
  const oversized = resolveProtectedPackageRange(
    "bytes=0-8388608",
    20_000_000,
  );
  assert.equal(oversized.valid, false);
  assert.equal(oversized.reason, "range_too_large");

  const suffix = resolveProtectedPackageRange(
    "bytes=-100",
    20_000_000,
  );
  assert.equal(suffix.valid, false);
  assert.equal(suffix.reason, "invalid_range");

  const beyond = resolveProtectedPackageRange(
    "bytes=25000000-",
    20_000_000,
  );
  assert.equal(beyond.valid, false);
  assert.equal(
    beyond.reason,
    "range_not_satisfiable",
  );
});
