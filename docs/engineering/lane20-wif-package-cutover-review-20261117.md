# Lane 20 — PROPOSED protected package-only WIF integration and controller cutover

**Date:** 2026-11-17.  
**Status:** DRAFT SOURCE-ONLY REVIEW. **DO NOT MERGE TO LIVE WORKER OR DISPATCH CLOUD.**  
**Owner direction:** Prepare and validate integration, not Cloud execution.

## Exact current checkpoint and remaining dependency
Re-read GitHub private worker controller file, blob **`24e3468dd67d96d541a383a2db93f585c9464b02`**. `mode=package,status=halted,ordinal=26,runID=43290954679,retryCount=2`. The failed claim expired **Nov 14, 2026**. Protected old controller source fingerprint **`ab8c5bc19ef079cdd36df45c13240aad17fa526ba5214e55e32a4bbdb63a32a8`**. Five failed allocations recorded, no refunds.

Last independently verified ordinal 23 receipt SHA **`1c54e40b0b8e50b5e030ebebf10b2384872664699ade365ecadeb2495e60e4f8`** covers 32 accepted immutable archive parts (`core-000..031`), no indexes. All 278,278 accepted raster positions and 34,750 source jobs must remain unchanged. Next **unaccepted** group consists of `core-032`, `core-033` and `leaf-on-000..005`.

## Safest source-code integration for isolated review
Original package worker `.github/automation/rrgh_package_runtime.py` imports `token` from the protected `rrgh_wif_credentials`. The proposed review swaps ONLY that import to `rrgh_fresh_oidc_token_candidate_20261117.token` for **both package-stage and package-verify**. It intentionally does not change the stage loop, receipt/claim identities, versioned GCS object references, independent readback, controller advance, original map source, or previously accepted archives. The new supplier mints a fresh job-scoped GitHub OIDC assertion on each <=120-second cache renewal, then performs direct Google STS exchange against the existing provider and same job identity. It must reject permanent IAM denials and never reuse stale credentials.

Crucial integrity change: the existing controller's protected **`CODE_FILES`** fingerprint in `.github/automation/rrgh_dispatcher.py` is extended to include the supplier's exact Python bytes. The supplier was deliberately outside the live CODE_FILES digest while source-only in PR139; it **must** become protected before production integration. No other WIF provider/IAM, key, workflow permission or token material is expanded.

**The original production credential helper `rrgh_wif_credentials.py`, its legacy installer `rrgh_credential_integration.py`, and `run_gorge_checkpoint_slot.py` remain unmodified.** That avoids unintentionally changing source-rendering workers. The credential-integration template validates the prior helper content, so globally replacing the helper would have broken its exact migration contract.

## Fingerprint / owner authorization boundary
The proposed protected code necessarily produces a **different** deterministic `rrgh_dispatcher.local_digest` than the historical `controlDigest`. Existing `rrgh_dispatcher.validate_state` refuses that mismatch even with `allow_upgrade=True` because the current state is `halted`, NOT the old `dispatching` state, and no matching `pendingControllerUpgrade` is present. Any proposed local owner upgrade must **fail closed**. This review deliberately does not modify `validate_state`, create a `pendingControllerUpgrade`, move the live status from halted, claim an allocation, extend the expired plan, update historical receipts, or add an owner request file.

Any later one-time owner-approved cutover must explicitly bind **both** new code fingerprint and old controller blob SHA, source SHA/plan SHA, 32-part receipt/checkpoint, sourceRequests=0, all five prior nonrefundable failures, original budget/GitHub ceiling and an exact new controller CAS. It cannot be an ordinary GitHub Actions job rerun. No such transition is implemented or authorized here.

## Strict offline verification — the proposed review branch only
New read-only `.github/workflows/rrgh-wif-package-integration-qa.yml` has `contents: read` and no `id-token: write`, Cloud SDK credentials, GH_TOKEN, or dispatch permissions. It pins the historical accepted source checkout and tests:
- immutable old controller Git blob SHA, last independently verified receipt, accepted archive count and failed claim;
- original raster-source WIF helper and credential-integration module Git blobs unchanged;
- new candidate plus package runtime both protected under controller `CODE_FILES`;
- old controller/source digest deliberately mismatches and `validate_state` refuses dispatch, including a forged old upgrade request;
- candidate replacement is the only package worker import change, stage/verify still share unchanged direct token provider;
- WIF permanent-denial `RuntimeError` remains **nonretryable** in `rrgh_package_runtime.transient`;
- fixed next-eight part allocation under original `PACKAGE_STOP=122.25` and monthly storage ceiling, source requests zero, $0.75 final-delivery reserve untouched;
- existing candidate's mocked direct-ST​S token tests and legacy WIF denial tests.

## Budget — verified narrow plan; full remaining product NOT certified
The halted controller's next eight unaccepted archive descriptors sum to 398,243,840 bytes and 12,479 source-listed files. Pure source-only evaluation of original `rrgh_package_funding.caps` and `gorge_campaign_budget.cost` yields about **$0.371666 incremental modeled ceiling** and **$98.447508 modeled cumulative** after one hypothetical new allocation, with estimated continuing storage **$1.601754/month**. Original billed expense unknown; no ledger entry. The original $125 ceiling, $2 completion margin, $0.75 protected delivery reserve and $2 monthly storage stop remain fixed. Cost model and accepted state cannot be treated as approval.

**Critical unresolved blocker:** The complete real inventory layout and its accepted metadata descriptors reside in protected, generation-pinned Cloud records. They are not available within GitHub source-only checkout. The synthetic layout QA exercises geometry and limits but explicitly does not certify real future archive/index sizes. Therefore this review **cannot truthfully certify the entire remaining package/three-index budget**. Before any live allocation, the full layout must be obtained from authorized read-only evidence, verified against its checksum/receipt and used to reconstruct all remaining allocations including previously retained failures.

## Conditions before ANY live integration
1. Exact reviewed source-only checks pass; independently review the new supplier's GitHub OIDC audience / provider claims and log redaction. WIF rejection root remains *not conclusively proven*.
2. Independently obtain/pin complete remaining real package layout and all three index descriptors, verify source IDs/previous receipts and conservatively account for all prior consumed failures. Both cost and storage must stay below original unexpanded caps.
3. Explicit separate owner approval for one-time SOURCE + controller digest transition, not implied by PR merge. A reviewed workflow must support **halted** package mode with a new state CAS and preserve all historical receipts/accepted claims, with no automatic rerun of ordinal 26.
4. Only after those checks may an owner-authenticated new bounded Cloud operation be considered. Verify accepted source and new WIF provider on a new claim, independently stage and verify exact packages, then three indexes. Catalog activation, signed lease, Day Hikes and physical owner iPhone acceptance remain later gated tasks.
5. On any identity denial, ambiguous stage receipt, unexpected source request, exceeded cap or unexpected controller change: stop without retries or invented refunds.

**No image generation, original-master edits, signing/release, iOS application changes, customer catalog activation, Cloud call, or verified invoice is performed by this review.**

Relevant source-only [PR139](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/139), current open [issue138](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/issues/138).
