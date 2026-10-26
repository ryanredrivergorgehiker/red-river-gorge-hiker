import test from "node:test";
import assert from "node:assert/strict";
import {
  publishedAgreement,
  receiptId,
  getAppAgreementStatusForUid,
  acceptAppAgreementForUid,
} from "../src/appAgreement.js";

const testEnv = {
  RRGH_APP_TERMS_PUBLISHED: "true",
  RRGH_APP_TERMS_VERSION: "1.0",
  RRGH_APP_TERMS_SHA256: "a".repeat(64),
  RRGH_APP_TERMS_URL: "https://example.test/approved/mobile-eula-v1",
  RRGH_APP_PRIVACY_URL: "https://example.test/privacy",
  RRGH_APP_TERMS_EFFECTIVE_AT: "2026-11-01T00:00:00.000Z",
};
function memoryStore() {
  const documents = new Map();
  function doc(path) {
    return {
      path,
      collection(child) { return collection(path + "/" + child); },
      async get() {
        return { exists: documents.has(path), data: () => documents.get(path) };
      },
    };
  }
  function collection(path) { return { doc: (id) => doc(path + "/" + id) }; }
  const db = {
    collection,
    async runTransaction(body) {
      return body({
        get: (ref) => ref.get(),
        create: (ref, data) => {
          if (documents.has(ref.path)) throw new Error("immutable receipt overwrite");
          documents.set(ref.path, data);
        },
      });
    },
  };
  documents.set("accounts/uid1", { status: "active" });
  return { db, documents };
}
function declaration(options = {}) {
  return {
    agreementId: "rrgh-mobile-terms-eula",
    version: "1.0",
    contentSha256: "a".repeat(64),
    method: "checkbox_accept_and_continue",
    affirmed: true,
    ageDeclaration: "adult",
    guardianPermission: false,
    ...options,
  };
}
test("filed draft cannot become a published legal agreement by default", () => {
  assert.equal(publishedAgreement({}), null);
  assert.equal(publishedAgreement({ ...testEnv, RRGH_APP_TERMS_PUBLISHED: "false" }), null);
  assert.equal(publishedAgreement({ ...testEnv, RRGH_APP_TERMS_SHA256: "draft" }), null);
  assert.equal(publishedAgreement({ ...testEnv, RRGH_APP_TERMS_URL: "http://example.test" }), null);
});
test("UID-bound acceptance requires explicit action, current hash, eligible age and guardian attestation", async () => {
  const { db, documents } = memoryStore();
  for (const values of [
    { affirmed: false },
    { method: "login" },
    { version: "0.3-draft" },
    { contentSha256: "b".repeat(64) },
    { ageDeclaration: "under13" },
    { ageDeclaration: "minor_guardian", guardianPermission: false },
  ]) {
    const result = await acceptAppAgreementForUid(db, "uid1", declaration(values), testEnv);
    assert.equal(result.accepted, false);
  }
  assert.equal(documents.size, 1, "invalid attempts cannot produce receipts");
  const status = await getAppAgreementStatusForUid(db, "uid1", testEnv);
  assert.equal(status.published, true);
  assert.equal(status.accepted, false);
  assert.equal(status.reason, "acceptance_required");
});
test("minor with permission writes one immutable server-timestamped receipt", async () => {
  const { db, documents } = memoryStore();
  const now = { toDate: () => new Date("2026-11-03T20:00:00.000Z") };
  const request = declaration({
    ageDeclaration: "minor_guardian", guardianPermission: true,
  });
  const first = await acceptAppAgreementForUid(db, "uid1", request, testEnv, now);
  assert.equal(first.accepted, true);
  assert.equal(first.reason, "accepted");
  const next = await acceptAppAgreementForUid(db, "uid1", request, testEnv, now);
  assert.equal(next.reason, "already_accepted");
  assert.equal(documents.size, 2);
  const status = await getAppAgreementStatusForUid(db, "uid1", testEnv);
  assert.equal(status.accepted, true);
  assert.equal(status.acceptedAt, "2026-11-03T20:00:00.000Z");
  const hash = receiptId(publishedAgreement(testEnv));
  const record = documents.get("accounts/uid1/appAgreementAcceptances/" + hash);
  assert.equal(record.guardianPermission, true);
  assert.equal(record.uid, "uid1");
  assert.equal(record.method, "checkbox_accept_and_continue");
  assert.equal(record.acceptedAt, now);
});
test("first Firebase UID can create active account plus immutable acceptance atomically", async () => {
  const { db, documents } = memoryStore();
  const first = await acceptAppAgreementForUid(db, "new-user", declaration(), testEnv);
  assert.equal(first.accepted, true);
  assert.equal(documents.get("accounts/new-user").status, "active");
  const status = await getAppAgreementStatusForUid(db, "new-user", testEnv);
  assert.equal(status.accepted, true);
});

test("different UID and material version receive no inherited legal acceptance", async () => {
  const { db, documents } = memoryStore();
  await acceptAppAgreementForUid(db, "uid1", declaration(), testEnv);
  assert.equal((await getAppAgreementStatusForUid(db, "uid2", testEnv)).accepted, false);
  const changed = { ...testEnv, RRGH_APP_TERMS_SHA256: "c".repeat(64) };
  assert.equal((await getAppAgreementStatusForUid(db, "uid1", changed)).accepted, false);
  assert.equal(documents.size, 2);
});
test("unpublished, inactive, or duplicate accounts cannot manufacture consent", async () => {
  const { db, documents } = memoryStore();
  assert.equal((await acceptAppAgreementForUid(db, "uid1", declaration(), {})).accepted, false);
  documents.set("accounts/uid1", { status: "deletion_pending" });
  assert.equal((await acceptAppAgreementForUid(db, "uid1", declaration(), testEnv)).accepted, false);
  assert.equal(documents.size, 1);
});
