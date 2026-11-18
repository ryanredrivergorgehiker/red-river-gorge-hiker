import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_CAPABILITY_TTL_SECONDS,
  MAX_PROXY_RANGE_BYTES,
  hashCapabilityToken,
  parseBearerToken,
  resolveProtectedPackageRange,
  regionalObjectGeneration,
  capabilityMatchesCurrentObject,
  validatePackageObject,
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


function syntheticRegionalStorage(metadata) {
  const requests = [];
  return {
    requests,
    storage: {
      bucket(bucket) {
        return {
          file(object, options) {
            requests.push({ bucket, object, options: options ?? null });
            return { getMetadata: async () => [metadata] };
          },
        };
      },
    },
  };
}

function genuineShape(overrides = {}) {
  return {
    storageBucket: "rrgh-nonproduction-protected-packages",
    objectName: "engineering/map-production/plans/sha/slots/00001/verified.bin",
    objectGeneration: "1794960002423784",
    byteCount: 1024,
    sha256: "a".repeat(64),
    version: "2026.11.10.regional.abc123",
    ...overrides,
  };
}

test("regional candidate generation is mandatory, canonical and not rounded", () => {
  const missing = regionalObjectGeneration("gorge-core", genuineShape({
    objectGeneration: undefined,
  }));
  assert.equal(missing.valid, false);
  assert.equal(
    regionalObjectGeneration("gorge-core-" + "a".repeat(64), genuineShape({
      objectGeneration: "",
    })).valid,
    false,
  );
  assert.equal(
    regionalObjectGeneration("gorge-aerial-leaf-on", genuineShape({
      objectGeneration: "0",
    })).valid,
    false,
  );
  assert.equal(
    regionalObjectGeneration("gorge-aerial-leaf-off", genuineShape({
      objectGeneration: "1.25",
    })).valid,
    false,
  );
  assert.deepEqual(
    regionalObjectGeneration("gorge-core", genuineShape({
      objectGeneration: "18446744073709551615",
    })),
    { valid: true, generation: "18446744073709551615" },
  );
  assert.deepEqual(
    regionalObjectGeneration("route-rte-0001", { objectGeneration: undefined }),
    { valid: true, generation: null },
  );
});

test("verified regional object metadata and every range bind the same generation", async () => {
  const pkg = genuineShape();
  const metadata = {
    size: "1024",
    generation: pkg.objectGeneration,
    metadata: {
      "rrgh-sha256": pkg.sha256,
      "rrgh-package-id": "gorge-core",
      "rrgh-version": pkg.version,
    },
  };
  const fake = syntheticRegionalStorage(metadata);
  const accepted = await validatePackageObject("gorge-core", pkg, fake.storage);
  assert.equal(accepted.ready, true);
  assert.equal(accepted.objectGeneration, pkg.objectGeneration);
  assert.deepEqual(fake.requests, [{
    bucket: pkg.storageBucket,
    object: pkg.objectName,
    options: { generation: pkg.objectGeneration },
  }]);
  // This file is the generation-pinned handle used by createReadStream.
  assert.ok(accepted.file);

  const replaced = syntheticRegionalStorage({
    ...metadata, generation: "1794960002423785",
  });
  const rejected = await validatePackageObject("gorge-core", pkg, replaced.storage);
  assert.deepEqual(rejected, {
    ready: false, reason: "package_object_mismatch",
  });
});

test("regional download fails before object read if pin is absent or malformed", async () => {
  for (const bad of [null, "", "0", "00017", "fake"]) {
    const pkg = genuineShape({ objectGeneration: bad });
    const fake = syntheticRegionalStorage({});
    const result = await validatePackageObject("gorge-core", pkg, fake.storage);
    assert.equal(result.ready, false);
    assert.equal(result.reason, "package_object_mismatch");
    assert.equal(fake.requests.length, 0);
  }
});

test("stale regional capability cannot read a changed generation, hash or length", () => {
  const pkg = genuineShape();
  const cap = {
    packageId: "gorge-core",
    objectGeneration: pkg.objectGeneration,
    packageSha256: pkg.sha256,
    packageByteCount: pkg.byteCount,
  };
  assert.equal(capabilityMatchesCurrentObject(pkg, cap), true);
  assert.equal(capabilityMatchesCurrentObject(
    genuineShape({ objectGeneration: "1794960002423785" }), cap
  ), false);
  assert.equal(capabilityMatchesCurrentObject(
    genuineShape({ sha256: "b".repeat(64) }), cap
  ), false);
  assert.equal(capabilityMatchesCurrentObject(
    genuineShape({ byteCount: 1025 }), cap
  ), false);
  assert.equal(capabilityMatchesCurrentObject(pkg, {
    ...cap, objectGeneration: null,
  }), false);
  assert.equal(capabilityMatchesCurrentObject(pkg, {
    ...cap, packageSha256: null,
  }), false);
  assert.equal(capabilityMatchesCurrentObject(pkg, {
    ...cap, packageByteCount: null,
  }), false);
  // Old route catalog, which predates the new regional generation pin,
  // retains the existing short-lived capability behavior.
  assert.equal(capabilityMatchesCurrentObject({
    objectGeneration: undefined,
    sha256: pkg.sha256,
    byteCount: pkg.byteCount,
  }, { packageId: "route-rte-0001" }), true);
});
