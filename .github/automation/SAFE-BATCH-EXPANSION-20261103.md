# Safe batch expansion — active implementation handoff, November 3, 2026

Owner reaffirmed the existing plan: keep verified production running, make larger batches safely resumable, then increase geographically grouped work using measured accepted tiles per complete cycle. The nine-to-twelve increment was an initial step. Do not treat it as a permanent target or replace implementation with repeated status audits.

## Current technical gap

At source 54810bc1c8f8daffc04809e3c0bca47a4eddbd2c, gorge_campaign.py already checks source bytes, source requests, attempts, retained seconds, wall-clock closure reserve, output size, working cache and disk headroom before a new child. It can emit a bounded-stop receipt and independently recover the completed outputs. That is not yet a complete general continuation contract.

The recovery result does not fully expose an independently reconciled completed/attempted/unattempted partition. rrgh_dispatch_audit.py, rrgh_prepare_dispatch_successor.py and the token-bearing rrgh_dispatcher.py publisher still generally expect every approved job either to succeed or to be a typed source-pixel gap. Partial failure exceptions are exact historical incidents and must not be generalized by changing constants.

Current native selection is 4 Hiking + 4 Terrain + 4 leaf-off. Each failed child retains 600 seconds; twelve failed reservations fit inside the 9,000-second producer slot with 1,800 seconds left. Blindly increasing counts breaks that worst-case reservation assumption.

## Next implementation deliverable

1. Define a receipt-backed clean bounded-stop outcome. Independently validate the exact immutable plan, ordered attempted prefix, successful checkpoint records, typed pixel-gap attempts, and genuinely unattempted suffix. A job with any ambiguous reservation or execution must never be classified unattempted.
2. Preserve source identity/ETag state and completed output on a normal resource stop. Distinguish this clean closure from fatal failure or interrupted closure; use existing exact recovery/salvage eligibility for ambiguous incidents.
3. Teach recovery, the credential-free successor planner and the independent trusted publisher the same validated partition. Preserve accepted jobs and consumed attempts/quarantines; enroll only genuinely unattempted work through a fresh immutable plan. Never replay the old allocation.
4. Add conditional batch admission: retain each child's full reservation before attempting it, enforce total slot caps and explicit checkpoint/recovery headroom, and allow unused candidates to carry forward. Do not weaken limits merely to make a larger count fit.
5. Test real producer/reader/planner/publisher transitions for time, source bytes, request caps, output/cache bounds, consecutive typed source failures, zero-progress stops, interrupted closure, duplicate dispatch, tampered partitions and crash after reservation. Tests must prove no accepted tile loss, no double attempts and no endless automatic zero-progress loop.
6. After exact-head QA, deploy the continuation contract at a safe controller boundary. Increase the next geographically grouped pilot only to a count supported by measured resource admission. Use actual total-cycle accepted tiles/hour and cache/source reuse to decide subsequent increments. A 256-job setting requires demonstrated resource and recovery fit; it is not the next blind setting.

Keep native production running while this branch is developed. Source gaps and general cross-wave/boundary overview production remain parallel backlog work. Do not change geography, resolution, layer requirements, WIF/IAM, budgets or unrelated branches.

## Deployment and rollback

This branch is an engineering workspace, never a source of historical controller state to merge wholesale. Fresh-read the moving controller/source heads before deployment; publish only reviewed code through the digest handoff with compare-and-swap. Roll back future selection prospectively, retaining all newly accepted output and attempt history.

Recovery PR89 addresses November 3's separate pre-admission GitHub HTTP500 incident. It does not implement larger batches. See https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/89 for exact QA/deployment evidence.
