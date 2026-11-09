# RRGH completion checkpoint — 2026-11-09

## Live resumption after GitHub mitigation

This section supersedes the older halted/no-running-job snapshot below. GitHub reported mitigation at 13:43 Eastern. On Ryan’s explicit request, fresh checks found no active or queued runs, preserved source e0551e17752606cc9baa8280f45ef6209d739362 and halted original wave1358. Owner request ed439580c6f7f8b4919742a0680b082be52ffcd2 launched successfully as42682892232. Recovery-only42682954260 was admitted; independent verifier129382268706 is running. Original bounded-stage is skipped, so production was not replayed. No additional accepted tiles are claimed before its receipt passes the controller audit. Existing V3 successor gates remain configured.

Five source-mask diagnostics completed successfully in42682993035, job129382233656; exact evidence: docs/engineering/evidence/source-boundary-mask-42682993035.json, commit245a903b6104685f0098d312e533cd4be6f7f0b1. Leaf-off17537/25329 has all1,048,576 pixels. Terrain and leaf-off17585/25301 and17512/25339 have zero missing pixels inside the requested AOI; all missing pixels lie outside it. This establishes source-mask evidence only, adds zero accepted tiles, and does not waive full-tile/terrain-halo checks. Further boundary engineering must preserve original output geometry and genuine source pixels. Diagnostic use:160 official requests/216,488,216 received bytes; zero Cloud requests/map writes/replayed production attempts. ChatGPT scheduled engineering task was rechecked disabled, nextRun=null.

## Earlier checkpoint and recovery history

This checkpoint supersedes earlier instructions to resume the ChatGPT engineering task. Ryan explicitly requested that task disabled; it was rechecked disabled, with no next run. Continue only within the original RRGH completion scope and existing resource limits.

## Verified inventory

- Required raster positions: 278,278.
- Independently accepted through wave1357: 267,476 (96.12%); remaining: 10,802.
- Remaining split at that boundary: 7,052 lower-zoom positions and 3,750 native positions represented by376 consumed jobs.
- Wave1358 saved108 fresh overview outputs, but none are added to accepted totals until independent recovery succeeds.
- All1,770 USGS lower-zoom positions are accepted. Shared sunlight count remains320.
- Phone-ready package closure and physical iPhone testing are NOT complete. Existing per-wave output/pixel/hash/package validation remains intact.

## Current live recovery boundary

Inspect live controller state before acting:
- Controller: lane20/offline-production-preflight-20261029
- Source: lane20/map-producer-iam-design-20261029
- Source SHA: e0551e17752606cc9baa8280f45ef6209d739362
- Wave1358 plan: d78942ef9eafbd3eeaf08f57392dce9cda356213d45e1c3c2b0bd3351d2a10b4
- Original production run:42669263145; dispatch a89729737b5a1001365d1b90575c3a14000658fd07c2b45a08eac0b32ae6e0eb.
- Producer129341314881 succeeded, saving108 outputs with zero official-source requests. Production step17:56:17–18:08:13UTC; this includes dependency bootstrap. Saved output bytes3,699,684.
- Producer receipt: engineering/map-production/plans/d78942ef9eafbd3eeaf08f57392dce9cda356213d45e1c3c2b0bd3351d2a10b4/slots/00001/receipt.json; generation1794247693485558; bytes857; SHA94f2ad8d683f93b7fa77ed097dd59992184c38ec81a00f12618a931949a04ea7.
- Original run failed with GitHub internal server error before independent-recovery or retain-failure jobs existed. Correlation621e2998-284b-4186-9d05-78edc1bcd7ed.
- Recovery-only dispatch42672888093 failed terminally with zero jobs and no controller claim. Its exact failed-head state, source/plan/dispatch and complete zero-job inventory were verified; a unique-head scan returned only that run. It is preserved in unstartedRecoveryDispatchHistory. No Cloud slot was executed.
- State was then restored to the original1358 halted production boundary, retaining launchCounter1315 and the failed recovery dispatch history. This is NOT a rollback of any accepted work or consumed Cloud allocation.
- As last checked: enabled=true, status=halted, mode=produce, runID42669263145; recoveryStartAuthorization pins the original producer receipt. Prospective crosswavePolicy is now V3, activated by commit d979aa7cdc1aa7ff348ecd2bcbe106d60b3587bc. The current producer source, plan, dispatch, saved receipt, accepted history and launchCounter remain unchanged. This policy only selects a successor after independent verification.
- Current controller digest: df8217c7a858c9a5f23bbea823ff1ae29c7ec508350b96679c0fe2369a1e5c38.
- Request commit536ee279e7f29037643eee787339f8114ee04ec5 asked only recover-unstarted. Launch42673314408 failed before any job, GitHub internal error b01ef2dc-f320-4d60-a6bf-3467e8a2ef9e.
- Existing main handoff was manually dispatched once after verifying its live code and original1358 boundary. Run42673794518 also failed with zero jobs, GitHub internal error fe1ebe82-0930-451c-87aa-bb0659991024.
- No production/recovery job is currently running. Do not claim background progress or that108 were accepted.
- No scheduled-task or cron configuration was enabled/changed. Existing GitHub handoff remains configured; its actual scheduling has been infrequent. Do not promise a15-minute recovery cadence.

## Deployed reviewed changes

PR108: exact four-parent zero-adjacent-edge receipt reconciliation; actual1357 receipt-only settlement42667762177 succeeded. No production replay.

PR109: bounded ordinary-child overview batches, max128 and unchanged3000ClassB/2GiB total funded read envelope. First batch108. Actual1357 planner through nonoverlapping larger batches passed. Dedicated QA42668554251 passed; repository contract passed, unrelated external catalog GBP/USD build failed. No storefront changes.

PR110: https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/110
- Head05a9d37dbab91f4475d1a47a465ca3bbca4ca47d; merge213bc93584b1d8fd234eef4df8435e43db053f29.
- Terminal GitHub scheduler failure with absent verifier is eligible only with complete first-attempt job inventory, successful producer/admission, no executed alternative job, skipped advance and original source/receipt pins.
- Existing main handoff can recover an orphaned running/halted state; it dispatches recovery only, never reruns production. Cloud create-only claims remain mandatory.
- Dedicated QA42672500382 passed, including actual1358 evidence, missing/foreign/started/ambiguous-job rejections, split recovery,27 handoff and16 publication regressions.
- General CI42672505979 failed before creating either job: internal server error ba3c36ca-d3ba-481b-8ae1-7d07b49aad5a. Failed-only rerun was rejected by GitHub as non-retriable. Later full CI for PR111 passed with this runtime included.

PR111: https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/111
- Head1209f7f593e974f2d91b8f6b8263366c9ccf9071; merge5926822aaf3c8f38947ac436f827fb382c1b4dd9.
- Typed read-only accepted-child readers for verified subsets, failed-worker partial recovery, missing-worker saved-checkpoint salvage and separately funded wave289 completion. Failed original allocation remains fully consumed; unresolved jobs never become accepted.
- Exact QA42672820240 and full CI42672826867 both passed.
- Actual1357 receipt -> synthetic108 ordinary batch -> typed4 pilot -> larger nonoverlapping batch was tested through the trusted publisher. Synthetic receipt tests are NOT live acceptance.
- Code is installed and V3 policy is prospectively enrolled. The controller audit first requires successful independent1358 verification; the planner then selects a four-parent live pilot covering recovery paths105,289,260. Larger typed batches remain blocked until that pilot independently verifies. Exact policy readback matched after enrollment; no new producer or recovery was dispatched by this state-only change.
- Prospective source-module migration allows only the exact existing PR109 hashes. Original geometry, renderer quality, accepted output bytes, failed attempts and aggregate budgets stay unchanged.

## Remaining work and safe continuation

1. When GitHub can schedule jobs, use the exact current recovery-start request or existing handoff to run the unused1358 recovery slot. First inspect live state/runs, avoid duplicate dispatches, and never rerun the original production workflow.
2. Independently verify all108 outputs and package chunks; receipt must bind the saved worker above. Only then accepted count can become267,584 and remaining10,694.
3. V3 is already configured prospectively. After1358 independently verifies, allow the tested planner to select the four-parent typed-reader pilot; larger typed batches require its independent acceptance. Do not mutate an active producer source or digest. Use the current inclusive ledger for any prospective code rollback.
4. Ordinary-only simulated queue adds5,480 parents from1357, leaving1,572 lower-zoom and3,750 native positions. This is a planning simulation, not actual accepted coverage or full-completion forecast.
5. Complete seed/boundary provenance:44 pre-campaign accepted jobs need explicit seed proof, including two existing hiking/terrainz15 parents. Do not invent ordinary campaign receipts for them.
6. Original native gaps:321 pixel-gap jobs/2,897 tiles plus55 other consumed jobs/853 tiles. All retain attempt1; global max remains2. Salvage saved bytes first for ambiguous cases. Do not clear attempts or blindly retry.
7.253 native jobs/2,401 positions have improved current source selection;123 jobs/1,349 positions have unchanged selection. Earlier actual full-mask diagnostics proved hiking-16-17534-25326 and terrain-16-17537-25329 fully covered by original official candidates. Leaf-off17537/25329 was unknown after the64MiB diagnostic cap, not a proven source hole.
8. Five additional source-only diagnostics are prepared on lane20/source-boundary-diagnostic-20261109, commitbfe518128351a81a2c05de1a245e6aa083766abc. Jobs: leaf-off17537/25329, terrain and leaf-off17585/25301, terrain and leaf-off17512/25339. Existing per-layer caps134,217,728bytes/200requests terrain and536,870,912bytes/750requests leaf-off;600sec/case. No GCS, map writes or native attempt consumption. Run42673355043 failed before creating a job; no new source evidence exists.
9. A bounded second-attempt native repair queue still needs engineering and proof: preserve original attempt/allocation, full mask and DEM halo validation, source identity and accepted bytes, explicit second-attempt accounting and independent recovery. Current fresh-territory planner correctly rejects previously consumed jobs; do not weaken that generally.
10. Final package assembly must join exact XYZ coverage across all zooms/layers, shared assets and historical receipt types. Native limits:256,000,000bytes/part;60,000 entries/part;64parts/group;1MiB authenticated index. Existing per-wave parts need consolidation, not an unbounded concatenated index. Validate all final parts and delivery path before marking ready for physical iPhone testing.

## Controls

- ChatGPT task6ae61fb61b048191b9992b9d5991fbe3, “RRGH Offline Map Engineering”: disabled, nextRun=null, rechecked this session.
- Existing campaign USD125, monthly modeled storage USD2, protected reserveUSD2 unchanged. Modeled ledger is not a bill or OpenAI compute cost.
- Last accepted1357 chargedUSD87.46516943344740867614746101 and storedBytes41,371,019,816. Current1358 admission includes its existing allocation, not yet independently settled.
- No IAM, account, geographic extent, quality, storefront, entitlement or physical-device acceptance changes.
- No credible full-completion date while live verification is blocked and native/boundary closure is unresolved. Report measured accepted throughput only after independent recovery.

## Local reproducibility

Workspace used: /workspace/scratch/a519ae7941df.
Deployed runtime/test changes are persisted in GitHub PRs108–111.
Local crosswave-typed-engineering contains committed PR110+111 code; crosswave-scheduler-engineering contains PR110 tests and actual incident fixture.
crosswave-batch-source and crosswave-typed-source contain synthetic successor fixtures; NEVER publish them as live source.
