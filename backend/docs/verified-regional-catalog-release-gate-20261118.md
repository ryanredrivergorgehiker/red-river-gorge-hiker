# Lane 20 — immutable regional catalog release preflight (2026-11-18)

## Authoritative state and scope
Owner approved proceeding after the physical iPhone QA successfully zoomed/panned one original Kentucky topo tile, not a true multi-tile regional map. Current protected worker-controller source branch `lane20/offline-production-preflight-20261029` reports `package-validation-waiting`, `verified-awaiting-catalog`, ordinal 41/run 44203971099, `122/122` independently verified regional archive parts and `3/3` indexes, with `packageBytesIndependentlyVerified=true`. Catalog candidate ref is recorded under `package.lastVerified.catalogCandidates`; `package.authority.activateCatalogs=false`. These are **immutable package receipt claims, not current active catalog or authorized iPhone downloads**.

## Source-only changes
- `backend/functions/src/delivery.js` now refuses new region-package catalog entries that omit a canonical *string* `objectGeneration`. It opens a Cloud Storage File with that exact generation, verifies returned generation plus size/SHA/custom metadata and uses the same pinned File for each bounded range. Legacy route and prior Gorge Base records remain generationless for compatibility.
- New capability receipts bind package SHA, byte count and object generation. `backend/functions/src/index.js` rejects a stale regional capability if any of those fields changes; customer UID/entitlement/access checks and 300s TTL remain unchanged.
- `backend/scripts/preflight_verified_regional_catalog_20261118.py` is an offline, read-only structural preflight. It takes a trusted, independently decoded complete candidate JSON document plus current controller JSON. It rejects partial 122+3 catalogs, wrong authority, premature activation flags, missing Base entitlement, wrong private bucket, noncanonical immutable generation, malformed/duplicate identity, SHA/bytes/version/metadata drift and missing group indexes. Results explicitly state that **no remote bytes were read back, no generation was reverified in GCS, no catalog was activated and no physical full-region map was accepted**. Unit tests use synthetic fixtures only.
- The candidate document itself is producer-record-encoded in immutable private GCS. The preflight deliberately does not assume a plaintext JSON encoding or claim that a locally decoded candidate has the exact same SHA as its GCS transport record. An independent authenticated downloader/decoder with object generation/SHA readback must establish that link.

## NONPRODUCTION release gates still mandatory
1. Verify exact `lastVerified` receipt/checkpoint and independent 122+3 candidates against the actual GCS object generation, byte count, SHA and object metadata, using least-privilege scoped identities and approved read budgets. No permissions are broadened.
2. Review *nonproduction-only* Firestore staged documents. Producer candidates are `active=false`, `contentReady=false`; do NOT silently change them to delivery-ready. Only the owner-governed, explicitly approved catalog transition should set the live required `active=true`, `lifecycle=active`, `deliveryState=ready`, with verified `objectGeneration`, source attribution and exact account Base requirements. No customer production publishing.
3. Exact-head native backend unit + emulator integration tests and iOS unit/phone build. This PR is **source only**, not compiled in GitHub CI or deployed by its existence.
4. Existing account-authenticated/lease-guarded 8MiB range downloader must verify signed index and every part, atomically install Core, preserve recorded hikes, and then perform real multiple-adjacent-tile airplane-mode iPhone UI tests through iOS draft PR #188.
5. Do not delete or regenerate original region rasters, unconditionally rerun failed Cloud stages, relax signed lease/UID/App Check, bypass budget limits, bind insurance, or release the app.

## Manual source-only preflight (requires independently obtained authentic files)
```bash
python3 backend/scripts/preflight_verified_regional_catalog_20261118.py \
  --controller <PRIVATE_VERIFIED_CONTROLLER_JSON> \
  --decoded-candidates <AUTHENTIC_DECODED_CANDIDATE_JSON>
python3 -m unittest discover -s backend/scripts \
  -p 'test_preflight_verified_regional_catalog_20261118.py' -v
```
This does not access Cloud, charge usage, alter customer records or authorize a release. The release remains blocked until genuine GCS readback and owner-governed catalog activation.

Issue: https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/issues/147
iOS dependency: https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker-ios/pull/188
