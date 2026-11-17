# Lane 20 — Recovered independently verified complete layout and full-budget bound

**Evidence date:** 2026-11-17. **Status:** source-only historical audit / no Cloud authorization.

## What was missing from the PR #140 review
The previous cutover review correctly refused to claim the entire remaining packaging/index budget from the ordinal-26 controller alone. The controller exposes only the next eight part descriptors, not the full immutable layout. We have now recovered **historical, already-executed and independently verified GitHub Actions receipts**, eliminating the need to read GCS again just to obtain a budget upper bound.

The package layout was originally built Nov 11 by restricted bot run [43089742588](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/43089742588):
- Stage job **130763515272**, `final-package-stage`, operation `layout`, original source code SHA `d17d0e335ac47e1f6d116e149992cc02d6e4a827`.
- Published real regional layout has **122 parts**, metadata SHA256 `4ab453e99f36c823fda0c1bc7dfc6de752ec8fbeb269a9eec8382f4e41f6e8a8`, immutable GCS object SHA256 `e9ba4e8b61bc5b2523e964711e8b2d9337ba7e810b47c363baa9fd2d741a5304`, generation `1794426287427172`. This is the **real** layout, not the synthetic geometry QA.
- Independent verifier job **130764452361** succeeded; verifier receipt SHA256 `653ecbf5e5c8ee4c53dbacc4e511d37bb8b5b7e025e7230fabf5f13721856ba2`, verified checkpoint SHA256 `a19e36cf638c1cd1d9901fabd3cdf15c5a69f4217c3cc25124d0eaf8278bbbbd`. `independentReadbackComplete=true`, sourceRequests=0.
- Existing protected `rrgh_package_runtime.verify` recomputes inventory/native layout, independently downloads/pixel-and-hash-validates every descriptor, checks exact canonical `records.describe`, and **re-runs `contract.budget_outlook(actual, carry)`** before accepting the layout. Thus the full-layout budget outlook was independently validated under the frozen rate/cap model.

Historical stage's original **complete** budget outlook was:
- All 122 archive parts **plus all three final indexes**: `remainingWorstCaseUSD=7.002964074742573499679565428`.
- Original modeled total at layout creation: `102.0801798223397970199584962` (including all future package/index work at that time, not a bill).
- Original all-in expected continuing storage `1.741435576893389225006103516` USD/month; 122 parts and three indexes included.

## Reconcile against the CURRENT halted controller, with no refund
Current private working-branch controller blob is `24e3468dd67d96d541a383a2db93f585c9464b02`, **package/halted ordinal 26**, run `43290954679`, last independent success `43271422615` at ordinal 23, 32 independently accepted parts (`core-000..031`), **zero** final indexes, 278,278 accepted raster positions/34,750 jobs, five historical failures retained, expired prior allocation (Nov 14).

Current modeled carry is `98.07584213409313559532165537` USD and `47,342,383,951` modeled stored bytes (not actual billed or verified GCS storage). The actual remaining count is **122 - 32 = 90 archive parts** plus 3 indexes.

A deliberately **conservative upper bound** adds the entire historical budget for **all 122 parts/indexes again** to the current carry, even though the first 32 are already accepted. There are NO refunds for any consumed historical allocation:

| Modeled bound (no future failures) | Amount |
| --- | ---: |
| Current historically retained modeled carry | $98.0758421341 |
| Re-add **entire 122-part + 3-index** verified forecast | $7.0029640747 |
| Conservative cumulative Cloud model | **$105.0788062088** |
| Including untouched $0.75 final-delivery reserve | **$105.8288062088** |
| Original package stop / overall ceiling | **$122.25 / $125.00** |
| Remaining package-stop headroom | **$17.1711937912** |

The source original storage rate is `monthly(stored)=Decimal(stored)/2**30*.036`. From the independent layout settlement, the preceding stored bytes were `43,836,942,245 - 33,419,643 = 43,803,522,602`. Invert the historical independently verified **all-in** projected monthly storage to recover precisely `51,940,339,242` modeled projected stored bytes, giving **8,136,816,640** original future modeled storage bytes. Add **all** of that again to today's modeled carry (again double-counting already accepted parts):
- Model stored bytes: `47,342,383,951 + 8,136,816,640 = 55,479,200,591`.
- Model continuing storage: **$1.8600851496/month** against existing **$2.00/month** ceiling; margin **$0.1399148504/month**.
- Original program's separate **GitHub $350 stop** remains a distinct requirement and has not been newly verified in this historical model.

**Limitations:** This is a valid conservative whole-layout budget *projection* for unchanged source, layout, rates and no new failures. It is NOT a current inventory re-download, not physical bytes installed on iPhone, and not a verified Google Cloud invoice. Storage headroom is tight. Repeating a full-layout-sized workload three times would exceed the storage ceiling; real future failed allocations are nonrefundable, and the protected funding/continuing storage stop must still run **at every exact new allocation**. No general permission for automatic retries, cost overrun or customer activation is implied. The exact remaining 90-part descriptors are still only available inside the already-verified immutable layout; the budget bound does not waive the per-part stage+independent verify requirement.

## How the source-only proof is replayed
`.github/automation/fixtures/rrgh-verified-full-layout-budget-evidence-20261117.json` captures source job/run IDs, immutable GCS object hash+generation, accepted checkpoint and historical layout outlook. `test_rrgh_full_package_historical_budget_20261117.py`:
1. Pins the current controller Git blob SHA, historical whole-layout object SHA, independent stage receipt and checkpoint IDs.
2. Reads the exact historical verified **122-part** projection and the current nonrefundable budget ledger without contacting GCS.
3. Re-runs the original pinned source `monthly` formula and reconciles byte-level storage and the $122.25 package stop.
4. Deliberately **re-adds all 122 parts + 3 indexes** after the current carry, producing a conservative bound on 90 remaining parts/indexes.
5. Demonstrates that extra blanket retries would violate monthly storage; retained failures are never refunded and no Cloud job is claimed.

A new GitHub-only `contents:read` QA workflow runs the proof with the original pinned source commit. It has no OIDC, Cloud auth, dispatch or write permission. The historical evidence SHA references are linked to the actual GitHub Action jobs, not guessed from descriptions.

## Next review decision
This resolves the **whole-layout model gap** that blocked funding review for the no-future-failure plan. It does **not** clear the separate permanent-identity-denial root uncertainty or the protected controller-source transition.

The next draft must bind the exact halted controller SHA, source SHA/plan, historic accepted 32-part receipt and layout proof, proposed PR #140 code fingerprint, five historical retained failures, expired ordinal-26 claim and full budget upper bound. The transition mechanism must preserve old state and refuse any unexpected concurrent GitHub owner or GCS IAM rejection. **Owner must explicitly authorize that one-time transition and any new Cloud request after reviewing the guard.** Do not merge PR #140 or click GitHub Actions **Re-run jobs** as a substitute.

This audit does not change app code, rasters, accepted archives, Cloud IAM, original photo masters, website, ledger, or authenticated customer delivery.
