# Offline map production: Gate C continuation, 2026-10-29

The dedicated producer identity and tiny checkpoint drill are complete.
GitHub run 40908702176, source 40c9ff16cfde2daf84b1428a1b31936db412efae,
passed all three jobs. Its logs confirm Base metadata access, explicit secret
denial, create-only HTTP 412, overwrite HTTP 403, and fresh-runner byte-identical
recovery. Do not rerun these checks or passing native CI. The workflow did
describe the checkpoint generation, but did not retain its numeric value in
the logs or pin the independent download to that generation; the production
adapter must record and use generation-specific recovery references.

`assess_map_production_costs.py` is a new **offline assessor**, not a dispatcher
or an integrated runtime spending guard. It accepts preserved forecast JSON
and explicit current billing/bucket/control evidence. Missing, stale,
nonfinite or over-budget inputs fail closed. Ten focused tests cover these
decisions without network or raster processing. A passing synthetic fixture
does not establish real spending headroom or a production-ready worker.

The preserved sample model is 564,951,223,050 source-cache bytes (526.152 GiB),
7,685,212,160 package bytes (7.157 GiB), and approximately 473 hours before
setup/retries. This is conservative extrapolation, not a new benchmark.

At the conditional single-region Standard rates of $0.02/GiB-month,
$0.12/GiB external transfer, $0.005/1,000 Class A and $0.0004/1,000 Class B:

| Scenario | Conditional modeled USD |
|---|---:|
| Retain entire source cache for one month | 10.5230 |
| Recover the entire source cache externally once | 63.1382 |
| Upload every estimated 64 KiB block separately: 8,620,472 objects | 43.1024 |
| Upload ideal 64 MiB cache packs: at least 8,419 objects | 0.0421 |
| Retain one package generation for one month | 0.1431 |
| Read one package generation externally once | 0.8589 |

Partial packs, spatial shard boundaries, manifests, reservations and retry
attempts increase operation counts. Pack immutable deltas, not one GCS object
per 64 KiB source block. Never restore the whole cache on every worker.
The producer cannot delete/overwrite; stopping compute does not stop storage
charges. No lifecycle/retention change or temporary-storage cleanup is assumed
or authorized by this plan.

A deliberately conservative **illustrative**, unapproved ceiling of 600 GiB
stored for one month, 10 GiB external reads, 50,000 Class A and 100,000 Class B
requests costs $13.49, or $16.188 including 20% contingency. It therefore does
not fit the earlier conditional $15 storage-only planning figure when treated
as a combined spending ceiling. The historical $5 project alert is not an
independently verified current hard cap. Neither amount is increased here.

Next engineering work is a bounded spatial-shard checkpoint adapter: preserve
all revision 3/4 caches and ledgers; checkpoint completed output/receipts and
reserve retries durably; use generation-pinned reads and create-only immutable
packs; enforce cumulative source bytes, GCS stored bytes, external bytes,
request counts and time before every operation. Reuse accepted private Base
vectors/weather without copying legacy raster quality. Evaluate selective
source-cache retention before proposing full-cache persistence. Regional
plans remain immutable; earlier executed plans are not rewritten.

Outstanding owner/account information is one current billing/configuration
snapshot: Actions used/remaining and verified $350 stop; existing GCS approved
remaining allowance/current reservations; bucket location, storage class and
existing retention/soft-delete/lifecycle configuration. Read-only evidence is
sufficient; do not grant the producer billing/IAM administration. Cloud Console
does not load in this session; the GitHub billing browser is signed out and
the connector does not expose account billing. Do not request another IAM
bootstrap or broaden trust.

No new Actions run, GCS object operation, paid job, source download, map
benchmark, protected merge or deployment is launched by this continuation.
Only the existing 53,038,186-byte revision 4 evidence archive was recovered;
its recorded SHA-256 matches. Complete regional production and physical iPhone
acceptance remain pending.

Sources: https://cloud.google.com/storage/pricing and
https://docs.github.com/en/billing/concepts/product-billing/github-actions
(checked 2026-10-29). Standard public hosted Ubuntu compute is free; this
does not imply free GCS storage/egress or disclose current account headroom.
