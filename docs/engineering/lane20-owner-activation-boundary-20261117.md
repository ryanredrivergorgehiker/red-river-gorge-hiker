# Lane 20 — owner-authenticated single-file activation gate

**November 17, 2026. PRIVATE SOURCE REVIEW. No live authorization, no Cloud access.**

## Correct trigger architecture

GitHub's `workflow_dispatch` requires the workflow file to exist on the repository default branch (public website `main`). Moving the private production controller there is out of scope. Instead, the new workflow `.github/workflows/rrgh-owner-package-recovery-activation.yml` uses **only a push to the existing private Lane20 working branch** that adds or modifies **exactly one owner-authorized consent file** `.github/automation/rrgh-package-owner-approval-20261117.json`. The workflow remains inert until this exact owner consent exists; this PR does **not** create that file.

The job requires GitHub-reported repository, full branch, workflow ref, actor and triggering actor equal to the established owner, first attempt only, single non-forced non-deletion commit, event sender identity, exact `before` parent and `after` commit hashes, and actual on-disk `git diff-tree` showing ONLY the consent JSON. The checkout fetches two commits for parent verification. An ordinary PR, bot push, manual rerun, main-branch push, stale SHA, ambiguous multi-commit push, or unrelated code change is denied before a token is passed.

## Locked one-time operation

The owner consent must be a distinct **exactly field-bound** JSON object, valid for at most 24 hours, including old halted controller Git blob SHA `24e3468dd67d96d541a383a2db93f585c9464b02`, old/proposed controller digest, PR140 exact candidate SHA, original accepted source/plan hash, independent 32-part receipt/checkpoint, five failed allocations, exhausted retryCount=2, next eight unaccepted archive IDs, exact new funded plan hash/cost, 122-part conservative no-extra-failure budget+storage, zero source raster requests, no catalog activation or app release. Additional new required pins bind the **exact Git blob SHA of the activation Python implementation, owner event runner, and workflow YAML**. No party can change these scripts and reuse an old approval unnoticed.

Before any write, the existing protected code fingerprint MUST equal PR140's reviewed digest. PR140 is still DRAFT and unmerged at this review. The runner validates the authenticated owner GitHub push and reads the consent without a credential, then a privileged step calls the existing one-time `execute()` function. That function independently reads the live controller, validates the original Git blob and immutable accepted receipts, frozen source branch, budget and platform stop, and absence of competing producers. It models ordinal27 exactly (same operation, carry, checkpoint, five failures and retryCount2) then performs ONE SHA-conditional state update, followed by the already-existing durable-claim CAS and at most ONE restricted workflow POST. Unknown outcomes do not trigger automatic retries. The new workflow itself has **no `id-token: write` or Google Cloud access**; only a subsequently authorized existing restricted package job has Cloud identity.

## Mandatory before actual activation

1. Independently inspect exact PR140 source, OIDC supplier behavior and hash, and separately review this owner activation source plus its CI at the final commit.
2. Confirm the unchanged GitHub account-level spending stop and original $125 Cloud / $2 monthly-storage ceilings. Independent historical full-layout forecast: 122 total parts, 32 already verified, 90 parts plus 3 indexes remain; modeled cumulative $105.078806 plus untouched $0.75 final reserve = $105.828806 under no further failures; modeled monthly storage $1.860085. These are **not invoices** or arbitrary retries.
3. Produce a **fresh** exact consent JSON only after code and worker are reviewed, re-compute the exact ordinal27 plan hash with its actual expiry and cost from the pinned source, and have the owner explicitly approve that single bounded Cloud dispatch. Do not synthesize or commit owner consent on the owner's behalf.
4. Explicitly approve the protected PR140 digest transition before any Cloud credentials or paid recovery. New WIF credential supplier still lacks real-provider acceptance evidence; a continued provider/IAM denial must fail closed.
5. Run only the owner-authenticated consent push when every review gate passes. Avoid GitHub Re-run; never reset consumed attempts or regenerate source tiles. After recovery, independently verify remaining archives and three final indexes; then authenticated catalog, signed offline lease, and physical iPhone airplane-mode UAT are separate gates.

## CI and preservation

New isolated workflow has only `contents: read`, no GitHub write, no Google Cloud credentials, no OIDC, no owner approval file and no production entrypoint execution. Security tests cover identity spoofing, multi-file/multi-commit push, stale checkout, wrong workflow, duplicate JSON, missing approval, no privileged token, CAS conflict, finite original budget and dispatch-failure no replay. Prior PR143's source-only CAS and full historical budget tests are re-run.

**No merge to public main, no activation/owner consent, no worker dispatch, no Cloud expense, no original raster/receipt rewrite, no iOS source or hike data change, and no customer delivery claim in this PR.**
