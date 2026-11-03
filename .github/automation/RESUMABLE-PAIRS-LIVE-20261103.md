# Two-worker and resumable-batch rollout: live results

PR92 was merged and deployed with accepted production history preserved. Two 12-job pilots and two 24-job pilots passed fresh-runner independent recovery and trusted publication. The successor is on the reviewed `active24` policy: two child workers, at most 24 eligible jobs per batch, unchanged combined resource admission. No fallback was needed.

| Wave | Mode | Accepted jobs | Verified tiles | Producer seconds | Dispatch → recovery seconds | Complete automatic cycle seconds | Tiles/hour, complete cycle |
|---|---|---:|---:|---:|---:|---:|---:|
| [267](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41700324935) | Serial baseline | 12 | 114 | 172.9 | 481 | 655 | 626.6 |
| [268](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41702045892) | Paired pilot | 12 | 112 | 132.2 | 384 | 447 | 902.0 |
| [269](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41703207345) | Paired pilot | 12 | 112 | 115.0 | 332 | 399 | 1010.5 |
| [270](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41704226143) | Paired pilot | 24 | 236 | 227.4 | 488 | 633 | 1342.2 |
| [271](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41705872708) | Paired pilot | 24 | 236 | 307.1 | 507 | 638 | 1331.7 |

Across the four pilots: **72 accepted jobs / 696 verified tiles**. The two 24-job pilots together delivered **1336.9 tiles/hour**, versus **626.6** for the immediately preceding serial baseline (2.13× observed). These consecutive batches use different source windows; the small sample is not a guaranteed future speedup.

Each pilot verified source identities, resource reservations and merged transfer histories; all submitted children joined; the accepted/consumed/untouched partition closed exactly. Normal pixel/hash/seam checks and all new native package chunks passed. There were no quarantined or untouched jobs in these four live pilots.

Immutable input reuse is installed and exercised. The reported cache-availability counter accumulates the inputs available across pairs; it does not measure unique bytes or avoided downloads. No download-savings claim is made.

The controller automatically returns the next fresh allocation to the preserved serial 12-job path on a cleanly closed failed/partial batch or a measured regression, and disables re-enrollment. It retains every accepted receipt, consumed attempt, source pin and budget charge. An interrupted or unverifiable closure stops without replay. Historical rollback branches are code references, never ledgers to restore.

Validation: exact reviewed `e6b1759f1c507ef8feaf49fb08180a645368dfd0`; CI41698222865 and QA41698213912 succeeded, covering 212 test executions and seven synthetic migration/planner/trusted-publication roundtrips. Fallback was tested synthetically; successful live pilots did not invoke it. Deployment `dc3666751faa9b1206a58f7f7d80d673a0917b64`; handoff was claimed on wave267. Existing wave266 was preserved.

Published through wave271: **13,589 accepted jobs / 139,894 raster tiles / 320 Sunlight assets**. The post-wave271 modeled carry is $24.8025; the $125 campaign ceiling, $2/month storage target and protected $2 completion reserve remain unchanged. Model accounting is not an invoice reading.

Full exact run, job, source, plan, generation/hash receipt references, timestamps, active policy and snapshot are in [resumable-pairs-live-20261103.json](evidence/resumable-pairs-live-20261103.json). This evidence branch is a historical record and must not be used to restore controller state. Read live controller state for later progress.
