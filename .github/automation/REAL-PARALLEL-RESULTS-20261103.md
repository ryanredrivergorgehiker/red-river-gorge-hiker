# Real parallel rendering trial — 2026-11-03

Completed successfully in [run 41691861095](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41691861095), job 126112632256, while the separate bounded-stage production job was still running. Reviewed code: 26a00926d56e8db592e7af969737870b73c4de81; deployment: f33f6b541917db266431daf7f12a9437c8ba1c71; PR91. Existing restricted WIF identity, no IAM changes or manual exports.

22 already-accepted interior leaf-on overview targets, 88 independently accepted and generation/hash-pinned original child tiles. Three rotated-order rounds for each worker count. Timing includes process setup, actual unchanged production overview rendering, and fresh-process output hash/pixel readback. Every trial used separate private output directories. Inputs stayed unchanged. No benchmark output was admitted to production coverage.

| Rendering workers | Median seconds for 22 outputs and readback | Speedup | Observed simultaneous renderers |
| --- | ---: | ---: | ---: |
| 1 | 1.033772 | 1.00x | 1 |
| 2 | 0.666544 | 1.55x | 2 |
| 4 | 0.579674 | 1.78x | 4 |

All output hash vectors matched: fa454b384832d361e38fec9bb7b5e18264a7fd5d7ed4e7bdc5d9944baead0383.

Input loading took 48.842774 seconds, with 179 GET requests and 3,316,452 reserved response bytes. Cloud writes: zero; official-source requests: zero; production claims: zero. Reservation $0.01 from the existing protected completion reserve, within the $125 campaign. This is a limit, not an invoice.

## Interpretation and next implementation

Parallel rendering is proven for this existing overview workload. It is not a measurement of native source-window production, protected package delivery, GCS checkpoint publication, or total-cycle accepted tiles/hour. Most trial time was input verification/loading, so adding rendering processes alone would barely change its total cold-input time. Use two workers as the next conservative source/overview integration pilot, with shared immutable input reuse and geographic batching; do not infer a 55% whole-campaign acceleration.

Next work: general clean partial-batch closure through recovery/planning/publication; generalized cross-wave verified-child catalogs and edge policy; disjoint source assignments with isolated mutable caches/checkpoints and a shared budget; measured full-cycle production pilot. The main producer remains one worker and at most twelve jobs. iPhone changes and offline device acceptance remain with the owner's stated testing sequence.

## Wave260 preservation

Prior run 41687927485 failed during credential refresh after nine durable jobs. Recovery 126101461714 verified 59 tiles. Exact receipt: df0b69c14fa1091ee2beb3f3046bb4bdbeca456fba0591b7d361bf2d461d75d0, generation 1793728567727399. PR91 pins that incident, retains the entire failed allocation's budget, quarantines leaf-off-16-17512-25319, and leaves leaf-off-16-17514-25318 and leaf-off-16-17515-25318 eligible because they were not attempted. Publisher-only continuation 41691495521 succeeded and published 138,356 raster tiles / 13,433 accepted jobs / 320 Sunlight assets through260, then launched261. No completed producer was replayed.

Validation: CI41690697298, QA41690689301; 198 unit/regression tests, actual partial-closure planning/publication roundtrip, and subsequent synthetic successor roundtrips. Rollback reference lane20/rollback-before-real-parallel-trial-20261103 is code history only; never restore its stale ledger.

## Live continuation confirmed

Wave261 run41691861095 completed production, independent recovery and advancement successfully. Recovery126114530559 verified12 jobs/122 new tiles, receipt SHA2564ae9a1cc311e6568d218f73d0c49e20b4ed199cd7e44e28249ee08cf5e2e36b8, generation1793729974549404. Controller published13,445 accepted jobs/138,478 raster tiles/320Sunlight through261 and automatically dispatched wave262 run41692999570. The two untouched wave260 jobs completed in261; the quarantined tenth job was not replayed. Production and trial runners both started18:15:11Z; trial finished18:16:59Z and producer finished18:18:29Z, so trial did not delay production completion or the handoff. Modeled Cloud settlement24.2466971274 USD plus the separately reserved0.01 USD trial allowance; not an invoice.
