# Lane 20 — WIF lifecycle failure: offline-only evidence and safe recovery design
**Review date:** 2026-11-16 ET  
**Status:** SOURCE-ONLY ANALYSIS AND NEGATIVE QA. NOT A CLOUD RECOVERY, FIX DEPLOYMENT, OR OWNER APPROVAL TO SPEND.

## Exact live checkpoint (fresh source, not historical inference)
- GitHub private backend worker branch `lane20/offline-production-preflight-20261029`; controller blob SHA `24e3468dd67d96d541a383a2db93f585c9464b02`, unchanged as inspected November 16.
- Controller `mode=package,status=halted,ordinal=26,runID=43290954679,retryCount=2`. The claimed cursor expired `2026-11-14T19:30:55Z`; it **cannot** be replayed.
- Exact independently verified last receipt: `core-000` through `core-031` (32 total) at ordinal 23; `verifiedIndexes=0`. Last receipt `1c54e40b0b8e50b5e030ebebf10b2384872664699ade365ecadeb2495e60e4f8`. Preserve original 278,278 accepted raster positions/34,750 jobs and every accepted archive hash, historical receipt and consumed allocation.
- Planned but unaccepted next batch: `core-032`, `core-033`, `leaf-on-000` … `leaf-on-005`.
- Modeled Cloud carry `$98.0758421340931`, **not an invoice**. Original `$125` campaign ceiling, delivery reserve `$0.75`, storage gate `$2/month` and separate GitHub budget stop remain unchanged.

## Verified timeline
1. Run [43254665601](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/43254665601) (screenshot #1448) failed on a protected Cloud-object read timeout; built-in bounded recovery succeeded.
2. Later authorized worker runs [43262443554](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/43262443554), [43267254383](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/43267254383) and [43271422615](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/43271422615) passed independent verification/controller advancement, accepting 32 total archive parts.
3. Ordinals 24 and 25, runs [43276263428](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/43276263428) and [43283644332](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/43283644332), hit transport timeouts and retained full allocations under the existing two-recovery limit.
4. Final [43290954679](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/43290954679) began its package-stage executable around 19:32 UTC and failed around 20:05 UTC after a `gcloud auth print-access-token` refresh failure. Sanitized evidence: `WIF_REFRESH_FAILURE {"attempt":1,"category":"rejected-or-invalid","retryable":false,"storageRequestStarted":false}`. Stage receipt retained full allocation, `sourceRequests=0`, `transientTransport=false`. `package-recover` correctly stopped: `Package failure is not eligible for bounded transport recovery`.
5. No new raster work, customer catalog activation, signed offline lease, final index verification, or iPhone acceptance is evidenced.

## Root-cause boundary: what we know and do not know
**Observed:** `.github/workflows/offline-map-restricted-dispatch.yml` grants `id-token: write` only to selected restricted jobs; `package-stage` uses `google-github-actions/auth@v3` with direct WIF and no `service_account`. The existing helper `rrgh_wif_credentials.py` caches a successful token for only 120 seconds, invokes `gcloud auth print-access-token` again when expired, retries only known transport responses and rejects identity denials without reusing stale credentials. The stage job is allowed to run up to 55 minutes; the final failure happened >30 minutes into stage work.

**External technical constraint:** The Google GitHub authentication README documents GitHub OIDC tokens expiring in about five minutes, with short maximum lifetimes for directly federated credentials:
- https://github.com/google-github-actions/auth/blob/main/README.md
- https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-google-cloud-platform
- https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines

**Inference, not a proven diagnosis:** A long single-worker assembly requiring repeated fresh federated credentials exposes a WIF-renewal failure surface. That is consistent with the >30-minute run and failure, but the original credential provider or gcloud error text was deliberately not logged. It could instead be a provider claim/attribute rejection, temporary upstream identity issue, or other permanent denial. This evidence does **not** justify expanding IAM or overriding `transientTransport=false`. An unrelated older issue #71 describes a different Wave022 attribute-condition denial and is not proof of this failure's cause.

## No-Cloud regression delivered with this review
`.github/automation/test_rrgh_wif_lifecycle_20261116.py` mocks `gcloud` and time; it checks:
- successful 120-second cache reuse and renewal; no increase in bearer lifetime;
- denial precedence over coincident transport words, no automatic denial retry;
- expired cached bearer never reused after identity rejection;
- only known transient 503 and process timeout permit the finite 3-attempt / 1+2-second sleep path;
- no raw stderr or token leakage;
- the exact current halted controller, last verified part count and receipt, unaccepted next eight, expired cursor and controller digest remain unchanged;
- existing `recovery_allocation` still requires `transientTransport=True`, preserves failed allocation and limits retries to two.

No GitHub OIDC id-token permission, Cloud credentials, storage/dispatch code or state write is provided to the QA job.

## Engineering path to an actual safe fix (NOT YET IMPLEMENTED)
1. **Reproduce safely** the credential provider lifecycle in mocks; identify whether renewal uses stale GitHub OIDC identity or a distinct rejection, without printing tokens, credential files, URLs containing identity parameters or raw stderr. Existing logs are insufficient to assert precise cause.
2. **Design bounded resumability at authenticated job boundaries**: evaluate per-part or a similarly shorter unit with a fresh approved GitHub OIDC context and exact verified checkpoint per unit. Keep final archive bytes/layout and already accepted 32 immutable; never treat a staged-but-unverified archive as accepted. A stage duration under five minutes must be *measured*, not assumed from file count.
3. **Reconstruct complete future funding** under the original `$125` ceiling, `$0.75` final-delivery reserve, `$2/month` storage allowance and existing GitHub limit; retain all failed allocations, including the permanent-denial attempt. Do not change existing WIF provider conditions, mint long-lived keys, invent refunds or fall back to unverified sources.
4. **Separately review and authorize a one-time controller code/digest cutover** pinned to exact halted controller SHA, last independently verified ordinal-23 checkpoint, original source SHA/plan, historic run identity and consumed attempts. Any future updated worker source requires explicit matched digest authority; the existing general `validate_state` guard must continue rejecting unreviewed changes.
5. Only then consider **one** newly funded owner-approved package continuation. Demand independent stage/readback receipts, controller CAS, all remaining archive parts and three final indexes. Authenticated catalogs and leases, Day Hikes and physical iPhone UAT are later gates. Stop on any new ambiguous or permanent credential rejection.

## Explicit non-actions
This PR does not modify protected `CODE_FILES`, the WIF provider, Cloud IAM, the existing dispatch workflow, controller state, official map assets, iOS code or Main. It neither runs `gcloud` nor creates or claims a new package allocation. Do **not** click `Re-run jobs` on the failed workflow.
