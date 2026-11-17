# Lane 20 — One-time halted-controller CAS + bounded dispatch implementation review

**2026-11-17 — SOURCE STAGED; NOT MERGED OR OWNER-AUTHENTICATED FOR LIVE EXECUTION**

## Exact reviewed state

- Current protected state stays `package/halted`, ordinal 26, failed run 43290954679, Git blob `24e3468dd67d96d541a383a2db93f585c9464b02`; live fingerprint `ab8c5bc19ef079cdd36df45c13240aad17fa526ba5214e55e32a4bbdb63a32a8`.
- All 278,278 rasters / 34,750 accepted jobs, the 32 independently verified `core-000..031` archives, independent receipt `1c54e40b0b8e50b5e030ebebf10b2384872664699ade365ecadeb2495e60e4f8`, 0 indexes, five prior failures and exhausted retryCount 2 remain durable.
- Proposed candidate source is **DRAFT PR140**, head `f6ccbc111751d17099232732e6e6e5fc04d10c00`, reviewed protected digest `9876ab579696c5ba0d3ea4246f326ba744ee090c12fc4afb3993c6c6d39a8875`. This module cannot pass its positive fingerprint gate on the current unmodified worker.
- Real November 11 independent 122-part layout; 90 archives plus three indexes remain. Historical **no-new-failure** cumulative Cloud planning USD105.0788062088, plus USD0.75 final delivery reserve; continuing modeled storage USD1.8600851496/month below $2. Figures are projections, not bills, and not approval for retries.

## What this staged callable implements

`.github/automation/rrgh_halted_package_cas_dispatch_20261117.py` provides **no command-line entrypoint** and is **not hooked to any live workflow**. A separately reviewed trusted manual workflow would need to call `execute(api, root, source, request, context)`. The module never creates its own authorization object.

1. Require actual owner-triggered first-attempt `workflow_dispatch` identity and exact private working branch, NOT bot actor, a rerun or push.
2. Read live controller via authenticated GitHub state API and require exact prior Git blob, accepted source/plan, failed ordinal, expired allocation, five failures, retryCount 2, next exact eight archive part IDs, signed-independent-receipt reference and preserved accepted raster totals. Also require checkout's historical controller file to match the exact blob.
3. **Only after candidate PR140 is properly reviewed/integrated**, require real CODE_FILES fingerprint to equal its exact reviewed digest. Historical layout/cost recomputation must pass original $122.25 package stop, $125 overall campaign ceiling and $2 monthly storage cap. The next actual allocation must use `rrgh_package_contract.allocate`, freeze old `carry` / previous checkpoint / five failed attempts / 32 independently accepted archive records and zero source network requests. It deliberately keeps `retryCount=2` so it does NOT restore an automatic retry allowance.
4. Require a separate **owner authorization object** with a 24-hour maximum valid window, exact old blob, new fingerprint and PR head, accepted receipt + full checkpoint, original source/plan, failed run/ordinal, next eight IDs, **new exact plan SHA and reserved modeled amount**, full budget figures, and explicit single-cloud-dispatch consent. Unknown/missing/extra fields or relaxed limits fail closed. This object is **not present in the repository**.
5. Confirm account-level GitHub spending protection, no active competing controller/producer, frozen accepted source ref and both legacy initiation fences.
6. Write the single `halted`→`package-ready` successor through existing exact GitHub blob-SHA CAS. After confirmed CAS, existing protected `dispatcher.dispatch` runs the already-implemented second fence check, records its durable `dispatching` claim by CAS, and makes exactly **one** existing restricted workflow POST. Any CAS conflict or ambiguous response halts; this function does **not** retry an uncertain dispatch.
7. Independent verification of the next eight GCS archives, remaining groups, all three final indexes, signed offline lease and physical owner iPhone airplane-mode acceptance remain mandatory. Successful dispatch is NOT delivery.

## Review-only QA / explicit blockers

New offline tests inject missing owner identity, wrong actor, rerun, stale blob, wrong digest, tampered accepted receipt/carry/old retry window, absent/expired approval, wrong plan/cost/source scope, full storage cap breach, competing CAS and post-CAS ambiguous dispatch. Positive test uses a fake API and spies that exactly one simulated CAS happens before one **mocked** dispatch. The QA workflow is `contents:read` only, with no action-write / id-token / GH_TOKEN / Cloud credentials or real `execute` invocation.

**No production workflow wired yet.** Before real use: independent exact-head source review of this code; candidate PR140 protected integration approval; verify accurate approval/expiration/approved funding values; validate production workflow event provenance, protected permissions and concurrency; end-to-end WIF rejection negative tests; explicitly approve **one** bounded Cloud authorization; ensure GitHub budget platform stop is still active. Only then consider a separate manual activation change.

**NO-GO until then:** Do not merge PR140, edit the controller/request file, create owner approval on Ryan's behalf, launch a worker, click Re-run, expand IAM, alter the original source or issue an app release. No original masters, private iOS hikes, website/GitHub Pages, or stored accepted GCS outputs touched.
