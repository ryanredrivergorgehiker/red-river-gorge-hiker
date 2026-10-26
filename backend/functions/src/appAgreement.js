import { createHash } from "node:crypto";
import { Timestamp } from "firebase-admin/firestore";

// LEG-DEC-0039. The filed v0.3 Word agreement is a PRELAUNCH DRAFT.
// There is deliberately NO default published document, version, or hash.
// A separately approved release supplies the exact immutable HTML/PDF URL,
// SHA-256 hash, version and effective date through deployment configuration.
const AGREEMENT_ID = "rrgh-mobile-terms-eula";

export function publishedAgreement(env = process.env) {
  const version = env.RRGH_APP_TERMS_VERSION;
  const sha256 = env.RRGH_APP_TERMS_SHA256;
  const termsUrl = env.RRGH_APP_TERMS_URL;
  const effectiveAt = env.RRGH_APP_TERMS_EFFECTIVE_AT;
  const privacyUrl = env.RRGH_APP_PRIVACY_URL;
  const published = env.RRGH_APP_TERMS_PUBLISHED === "true"
    && typeof version === "string" && /^[a-zA-Z0-9._-]{1,32}$/.test(version)
    && typeof sha256 === "string" && /^[0-9a-f]{64}$/.test(sha256)
    && [termsUrl, privacyUrl].every((url) => {
      if (typeof url !== "string") return false;
      try { return new URL(url).protocol === "https:"; } catch { return false; }
    })
    && Number.isFinite(Date.parse(effectiveAt ?? ""));

  return published ? Object.freeze({
    agreementId: AGREEMENT_ID,
    version,
    contentSha256: sha256,
    termsUrl,
    privacyUrl,
    effectiveAt,
  }) : null;
}

export function receiptId(manifest) {
  // Binds the historical receipt to the exact legally published text, not
  // merely an informal version string or a mutable page URL.
  return createHash("sha256")
    .update([manifest.agreementId, manifest.version, manifest.contentSha256].join(":"))
    .digest("hex");
}

function accountRef(db, uid) {
  return db.collection("accounts").doc(uid);
}
function receiptRef(db, uid, manifest) {
  return accountRef(db, uid).collection("appAgreementAcceptances").doc(receiptId(manifest));
}

export async function getAppAgreementStatusForUid(db, uid, env = process.env) {
  const manifest = publishedAgreement(env);
  if (!manifest) return {
    uid, published: false, accepted: false, reason: "agreement_not_published",
    agreementId: AGREEMENT_ID, version: null, contentSha256: null,
    termsUrl: null, privacyUrl: "https://redrivergorgehiker.com/privacy/",
    effectiveAt: null, acceptedAt: null,
  };
  const snapshot = await receiptRef(db, uid, manifest).get();
  const receipt = snapshot.exists ? snapshot.data() : null;
  const accepted = receipt?.uid === uid
    && receipt?.agreementId === manifest.agreementId
    && receipt?.version === manifest.version
    && receipt?.contentSha256 === manifest.contentSha256
    && receipt?.method === "checkbox_accept_and_continue"
    && receipt?.affirmed === true
    && typeof receipt?.acceptedAt?.toDate === "function"
    && Number.isFinite(receipt.acceptedAt.toDate().getTime());
  return {
    uid, published: true, accepted, reason: accepted ? null : "acceptance_required",
    ...manifest, acceptedAt: accepted ? receipt.acceptedAt?.toDate?.()?.toISOString() ?? null : null,
  };
}

export async function acceptAppAgreementForUid(
  db, uid, declaration, env = process.env, now = Timestamp.now(),
) {
  const manifest = publishedAgreement(env);
  if (!manifest) return { accepted: false, reason: "agreement_not_published" };
  // Explicit human action is REQUIRED; signing in or using an already
  // purchased/leased account never manufactures this receipt.
  if (declaration?.affirmed !== true
    || declaration?.agreementId !== manifest.agreementId
    || declaration?.version !== manifest.version
    || declaration?.contentSha256 !== manifest.contentSha256
    || declaration?.method !== "checkbox_accept_and_continue"
    || !["adult", "minor_guardian"].includes(declaration?.ageDeclaration)
    || (declaration.ageDeclaration === "minor_guardian"
      && declaration.guardianPermission !== true)) {
    return { accepted: false, reason: "affirmative_acceptance_required" };
  }
  const account = accountRef(db, uid);
  const ref = receiptRef(db, uid, manifest);
  return db.runTransaction(async (transaction) => {
    const [accountSnapshot, receiptSnapshot] = await Promise.all([
      transaction.get(account), transaction.get(ref),
    ]);
    // Firebase authentication establishes the UID. The account document
    // might not yet exist if this is a new registration and its initial
    // account-state request is still in flight. Create both atomically.
    // Existing suspended/deletion-pending accounts remain ineligible.
    if (accountSnapshot.exists && accountSnapshot.data()?.status !== "active") {
      return { accepted: false, reason: "account_not_active" };
    }
    if (receiptSnapshot.exists) {
      // Immutable evidence; repeated retries are idempotent.
      return { accepted: true, reason: "already_accepted",
        uid, ...manifest };
    }
    if (!accountSnapshot.exists) {
      transaction.create(account, {
        status: "active", createdAt: now, policyVersion: 1,
      });
    }
    transaction.create(ref, {
      uid,
      agreementId: manifest.agreementId,
      version: manifest.version,
      contentSha256: manifest.contentSha256,
      effectiveAt: manifest.effectiveAt,
      method: "checkbox_accept_and_continue",
      affirmed: true,
      ageDeclaration: declaration.ageDeclaration,
      guardianPermission: declaration.ageDeclaration === "minor_guardian",
      acceptedAt: now,
      source: "ios_native",
      // Do not store DOB, GPS, device fingerprint, or signatures.
    });
    return { accepted: true, reason: "accepted", uid, ...manifest };
  });
}
