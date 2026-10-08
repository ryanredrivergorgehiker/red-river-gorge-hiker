# RRGH Offline Entitlement Lease Contract v1

Status: FROZEN ADDITIVE NONPRODUCTION CONTRACT  
Authority: LEG-DEC-0035  
Existing protected-package authorization and five-minute delivery capability behavior remains unchanged.

## Callable operation

Authenticated rrghAccountApi request:

```json
{
  "operation": "issueOfflineAccessLease"
}
```

A valid Firebase Authentication identity is required. The backend always binds the lease to request.auth.uid; there is no client-supplied uid.

Successful issuance response:

```json
{
  "issued": true,
  "reason": null,
  "lease": {
    "format": "compact_jws_rs256_v1",
    "algorithm": "RS256",
    "keyId": "<google-service-account-signing-key-id>",
    "signedToken": "<compact JWS>"
  },
  "verificationKeys": [
    {
      "keyId": "<key-id>",
      "algorithm": "RS256",
      "publicKeySpkiBase64": "<DER SubjectPublicKeyInfo, base64>"
    }
  ]
}
```

Denied/unavailable issuance response:

```json
{
  "issued": false,
  "reason": "account_not_active | no_effective_access | backend_temporarily_unavailable",
  "lease": null,
  "verificationKeys": []
}
```

## Signed token

Format: compact JWS using RSASSA-PKCS1-v1_5 with SHA-256 (RS256).

Protected header:

```json
{
  "alg": "RS256",
  "typ": "RRGH-OFFLINE-ENTITLEMENT-LEASE",
  "v": 1
}
```

Signed payload fields:

```json
{
  "schemaVersion": 1,
  "policyVersion": 1,
  "policyId": "LEG-DEC-0035",
  "leaseId": "<random opaque lease id>",
  "uid": "<Firebase uid>",
  "issuedAt": "<RFC3339/ISO-8601 UTC>",
  "validUntil": "<RFC3339/ISO-8601 UTC>",
  "renewAfter": "<RFC3339/ISO-8601 UTC or null>",
  "grants": ["base", "backpacking", "off_trail"],
  "trial": false,
  "trialEndsAt": null,
  "entitlementRevision": "sha256:<canonical-state digest>"
}
```

Canonical grants are only `base`, `backpacking`, and `off_trail`. Day Hikes are derived locally from a valid `base` grant and are never a separate signed grant. `backpacking` and `off_trail` may only appear when permanent `base` is also active.

For permanent paid access:
- `validUntil` is exactly 90 days after `issuedAt`.
- `renewAfter` is 30 days before `validUntil` (60 days after issuance).
- Silent authenticated renewal should be attempted whenever online after `renewAfter`, and may occur earlier on any authoritative reconciliation.
- A newly successful authoritative response replaces the previous usable lease immediately.

For Base trial:
- `grants` is exactly `["base"]`.
- `trial` is `true`.
- `trialEndsAt` is the authoritative server trial end.
- `validUntil` is never later than `trialEndsAt`.
- `renewAfter` is `null`.
- `issuedAt` is the signed server-time anchor for native trusted-time calculations.

## Native verification and trusted time

The client must fail closed unless all of the following are true:
1. JWS header exactly matches the supported algorithm/type/schema.
2. `keyId` resolves to a cached server-delivered verification key whose algorithm is RS256.
3. The JWS signature verifies over the exact protected-header/payload bytes.
4. `schemaVersion=1`, `policyVersion=1`, and `policyId=LEG-DEC-0035`.
5. Signed `uid` equals the currently signed-in/cached RRGH account uid.
6. Grants are canonical and every optional extension also has Base.
7. Current trusted time is before `validUntil`; for a trial it is also before `trialEndsAt`.
8. The lease is structurally well formed.

Paid cold-restart time rule:
- Preserve the last trusted server/wall-clock observation and monotonic observation in app-private state.
- During one boot, advance trusted time using monotonic elapsed time; do not let a wall-clock rollback move trusted time backward.
- Across reboot, paid access may continue only when the new wall clock has not moved backward behind the persisted trusted lower bound and the signed `validUntil` has not passed. If rollback cannot be safely reconciled, fail closed pending online verification.

Trial cold-restart time rule is stricter:
- While the same boot/monotonic epoch continues, trusted trial time is `issuedAt` plus monotonic elapsed time from the server-anchored receipt point, bounded by `trialEndsAt`.
- If the app cannot prove monotonic continuity (including reboot) or detects unresolved clock rollback/manipulation, trial access fails closed until successful online server validation.
- Device wall clock alone must never extend trial access.

## Key distribution and rotation

The server signing private key is never delivered to the client and is never stored in source. Nonproduction uses the existing Google runtime service-account signing authority through IAM Credentials `signBlob`; no KMS or paid signing service is introduced.

Each successful issuance returns the currently published public verification key set. The client:
- caches verification keys in app-private storage keyed by `keyId`;
- verifies a lease only with its exact signing `keyId`;
- adds newly received keys after successful authenticated server contact;
- retains a previously trusted public key while an unexpired locally stored lease still references it;
- may discard an old key once no retained unexpired lease references it;
- fails closed on an unknown key id while offline.

This permits normal Google service-account signing-key rotation without making old leases unverifiable merely because the server has rotated to a new key.

## Account transitions and revocation

- A successful online `issueOfflineAccessLease` result is authoritative and immediately supersedes local lease state.
- `account_not_active` or `no_effective_access` clears usable local lease authorization immediately.
- Refund/revocation learned online removes the affected grant from the newly issued lease; if Base is lost, no optional extension may remain effective.
- Backend/network failure does not invalidate an otherwise valid unexpired signed lease.
- Lease expiry has no unsigned grace period.
- Logout clears usable lease authorization immediately but ordinary logout may leave integrity-valid downloaded bytes locked/app-private for same-account reuse after future verification.
- Account switching cannot reuse another uid's lease.
- Account deletion clears lease authorization and requires purge of locally installed protected packages for that deleted account.
- LEG-DEC-0034 recorded-track data is not part of this contract and must not be transmitted, signed, uploaded, purged on ordinary logout, or otherwise coupled to lease issuance.

## Stable verification failures

Native code should normalize lease failures to:
- `lease_malformed`
- `lease_policy_unsupported`
- `lease_key_unavailable`
- `lease_signature_invalid`
- `lease_uid_mismatch`
- `lease_entitlement_mismatch`
- `lease_expired`
- `lease_time_untrusted` (native trusted-time/anti-rollback failure)

These are local verification outcomes, not new server entitlement sources.

## Test fixture rules

Backend automated tests generate ephemeral RSA signing keys at test time and exercise:
- permanent Base + both extensions;
- permanent-Base prerequisite;
- exact 90-day paid validity and 30-day proactive-renewal boundary;
- Base-only trial and authoritative trial-end cap;
- expired lease;
- wrong uid/account switch;
- forged payload and malformed signature;
- unsupported policy version;
- key rotation/old-key compatibility;
- account deletion and refund/revocation reconciliation;
- offline verification without backend availability;
- absence of recorded-track/location fields.

No production private signing key or protected route geometry is included in test fixtures or source.
