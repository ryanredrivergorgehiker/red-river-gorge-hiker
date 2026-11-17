# Lane 20 — Fresh OIDC direct-WIF candidate: receipt-safe package continuation

**Date:** November 17, 2026  
**Owner direction:** Proceed with engineering design and source-only tests.  
**Classification:** PROPOSED CREDENTIAL FIX / OFFLINE QA ONLY. **NO LIVE CLOUD AUTHORIZATION OR DEPLOYMENT.**

## Decision: smallest bounded integration first
The existing funded package stage and independent verification operate on one exact eight-part batch: stage slot 0 publishes one complete receipt, verifier slot 1 independently rereads immutable remote objects, and the separate controller checks both receipts before accepting the batch. Splitting stages into separate GitHub jobs would require additional protected slot-allocation and per-part receipt orchestration. An unaudited job matrix or partial stage receipt would weaken the existing acceptance contract.

A smaller candidate is to retain the original package runner and archive contract while replacing its **WIF token provider only** after separate review. The candidate `.github/automation/rrgh_fresh_oidc_token_candidate_20261117.py` currently is not imported by any live runtime. Under the existing `id-token: write` job, it obtains a freshly minted GitHub job OIDC JWT each time the 120-second access-token cache expires, then exchanges that assertion at Google's **fixed** Secure Token Service (STS) endpoint for a new direct-federation access token. It never impersonates a service account, stores persistent keys or credentials, or changes WIF IAM/provider policy.

This preserves the immutable batch layout, original two funded slots, receipt hash/generation binding, independent verification, per-slot meter and GCS generation checks. It is intended to remove the static-GitHub-assertion renewal exposure. It **will not** overcome a genuine provider attribute-condition rejection or unrelated IAM denial; such failures stop immediately.

## Exact verified predecessor — immutable
Live private backend controller blob `24e3468dd67d96d541a383a2db93f585c9464b02`, still `package/halted` ordinal 26, failed run `43290954679`, retryCount 2, current claim expired `2026-11-14T19:30:55Z`, five historic failures retained. Original 278,278 raster positions / 34,750 jobs and 32 independently verified archive parts (`core-000` to `core-031`) are protected. Last verified checkpoint ordinal 23 receipt SHA `1c54e40b0b8e50b5e030ebebf10b2384872664699ade365ecadeb2495e60e4f8`; `verifiedIndexes=0`, final delivery false.

The next unaccepted exact batch is `core-032`, `core-033`, `leaf-on-000` through `leaf-on-005` — 8 archives, 398,243,840 modeled archive bytes and 12,479 source-listed files. None may be assumed accepted because the stage and independent verify failed.

## Why a fresh GitHub assertion is a suitable candidate (not proof of cause)
The original `rrgh_wif_credentials.py` obtains a Google access token via `gcloud auth print-access-token` and caches it for 120 seconds, but the `google-github-actions/auth@v3` direct-federation action generates initial job credentials using a short-lived GitHub OIDC assertion. GitHub's runner exposes `ACTIONS_ID_TOKEN_REQUEST_URL` and `ACTIONS_ID_TOKEN_REQUEST_TOKEN` to authorized jobs for requesting GitHub OIDC assertions; Google's Security Token Service supports direct OIDC token exchange without a key. The original fatal stage run failed after ~33 minutes with `WIF_REFRESH_FAILURE category=rejected-or-invalid`, no continued transport retry, sourceRequests=0. **The real rejection cause is not conclusively known** because raw credential errors were intentionally redacted. The candidate must never turn identity rejection into an automatic retry.

Documentation:
- https://docs.github.com/en/actions/reference/security/oidc
- https://github.com/google-github-actions/auth/blob/main/README.md
- https://cloud.google.com/iam/docs/reference/sts/rest/v1/TopLevel/token
- https://google.aip.dev/auth/4117

## Candidate security design
1. Require exact current private repository, protected working ref, original restricted workflow path, `workflow_dispatch`, GitHub bot actor and run attempt 1 **before** requesting an OIDC JWT. Merely opening this candidate in an unrelated GitHub job cannot authorize it.
2. Require the runner-issued HTTPS OIDC token endpoint hostname under `*.actions.githubusercontent.com`, no redirects, unexpected ports, embedded alternate audience or URL control bytes. Do not write runner request tokens, GitHub JWTs, Google access tokens or transport bodies to logs or files.
3. Request a new GitHub OIDC token for the same provider audience already trusted by the original `google-github-actions/auth@v3` action. Exchange only against `https://sts.googleapis.com/v1/token`; assert fixed STS audience, grant type, access-token type and `cloud-platform` scope. The unchanged Cloud provider validates the JWT independently.
4. Reject malformed response, wrong token class, short/implausible expiry, invalid worker identity, HTTP 400/401/403 or unknown errors immediately. Never return the old cached bearer after a failed renewal. Allow **only** known 408/429/5xx and explicit transport timeouts to retry at most twice inside the process; failed storage writes are never retried by the candidate.
5. Cache a successful bearer for at most 120 seconds and no later than its advertised expiry minus 60 seconds. This does **not** extend credential lifetime or Cloud IAM trust.
6. Leave the original controller `CODE_FILES` fingerprint, stage code, package receipts, GCS checks, budget estimator, IAM/provider, historical verification and iOS code completely unchanged on the working branch. The candidate is not wired to production.

## Offline tests and limits
A GitHub-only workflow `rrgh-wif-fresh-oidc-candidate-qa.yml` runs mocked GitHub OIDC + Google STS operations and **has only contents:read permission**. It has no `id-token: write`, no Cloud credentials, no Google Cloud SDK and no dispatch permission. Mocked tests cover:
- exact GitHub workflow/ref/attempt/actor identity and OIDC endpoint;
- successful GitHub assertion + correctly formed Google STS request with the original provider;
- simulated 55-minute job requiring many fresh assertions;
- 120-second cached bearer maximum, and shorter advertisement/clock bounds;
- hard STS HTTP 403 and rejected renewal without fallback, header/audience/redirect/host validation;
- bounded HTTP 503 or timeout retries, no raw token, exception, request body or URL logging;
- original controller/source digest unchanged and live package worker **not importing** this candidate.

A passing mocked source-only test demonstrates source behavior, not the real provider's acceptance or network performance. Future exact-source integration QA must test the actual worker import against the candidate and deliberately fail prior controller fingerprint validation without authorized cutover. Real Cloud proof cannot happen until owner approves that cutover.

## Budget — modeled next batch only, NOT an invoice
From the *existing* `rrgh_package_funding.caps`, `rrgh_package_ingress.reservation` and original `gorge_campaign_budget.cost` rate formula, re-evaluating the eight unaccepted part descriptors in the unchanged ordinal-26 controller gives a hypothetical **new** two-slot allocation:

| Controlled planning quantity | Model |
| --- | ---: |
| Next eight archives / source-listed files | 8 / 12,479 |
| Modeled exact combined archive bytes | 398,243,840 |
| New allocation storedBytes ceiling | 431,798,272 |
| New allocation egressBytes ceiling | 1,321,234,820 |
| Class A / Class B request ceilings | 194 / 12,703 |
| Additional worst-case modeled charge | ~ $0.371666 |
| Cumulative modeled charge **if a fresh allocation were approved** | ~ $98.447508 |
| Including protected $0.75 final-delivery reserve | ~ $99.197508 |
| Modeled monthly storage after such allocation | ~ $1.601754 |
| Original program Cloud ceiling / protected package stop | $125 / $122.25 |

These figures exclude still-unknown later archive/index operations and any other failed attempts; they are **not** a new owner spending authorization, a bill, a fresh allowable controller allocation or proof that the *entire* remaining product fits. The original $125 hard ceiling, $0.75 final reserve, $2 completion buffer, $2/month storage cap, separate GitHub $350 hard stop, and zero-source-request rule remain in force. Reconstruct the **full remaining** immutable layout and funding in a later pure analysis before any Cloud work, retaining all prior consumed allocations. Do not post budget models to the ledger.

## Proposed subsequent gates — not executed here
1. Candidate passes exact-head no-Cloud QA and repository CI; verify only new candidate/test/workflow/design files changed. Merge this **unwired** candidate only to private Lane 20 working branch; merging must not alter controller fingerprints, state, WIF trust, or Cloud operations.
2. Independently review detailed renewal security (including exact GitHub id-token runtime behavior and the original WIF provider claims) and fully rebuild remaining archive/index funding and failure envelopes, with original accepted checkpoint and no hidden refunds.
3. Under a separate explicit owner-authorized one-time controller transition, wire reviewed candidate into protected `rrgh_wif_credentials.py` / package runtime and prepare a distinct future allocation for the expired claim. Enforce original digest CAS, exact halted state SHA, original immutable receipts, consumed retry history, source plan, delivery reserve and Cloud caps; verify prior worker can never be dispatched by PR/test event.
4. Only then contemplate **one** newly authorized restricted Cloud attempt. Validate fresh GitHub OIDC then STS and all stage/verify receipts without exposing credentials. Any identity denial, expired claim, unverified bytes, unclear billing or source regeneration must fail closed.
5. Continue remaining archives and all three independent indexes, authenticated/nonproduction catalog+lease, required Day Hikes and physical owner iPhone airplane-mode acceptance. iOS bugs remain a later task.

**STOP SIGNAL:** Neither this design nor mocked QA authorizes Cloud actions or a GitHub 'Re-run jobs' click. Issue #138 remains OPEN until actual runtime integration and independently verified delivery gates.
