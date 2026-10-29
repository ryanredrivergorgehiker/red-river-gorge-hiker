# Gate C compact reservations and offline regional forecast

This source-only continuation does not dispatch Actions or access GCS. It does
not enable regional execution or grant spending authority. The accepted live
recovery drill remains valid; no dedicated repeat drill is required.

## Compact records and cumulative controls

New plans opt in with `bookkeepingProfile: compact-v2`. Omitted profiles retain
legacy 1 MiB claim + 1 MiB final-receipt reservations, so old plan hashes and
stored records remain unchanged. New claims reserve 4 KiB and final/job records
are bounded at 16 KiB encoded. Both claim/final writes and metadata responses
are reserved atomically before the first create operation.

Records use deterministic lossless zlib encoding with a versioned magic prefix.
SHA256 and GCS MD5 cover the stored bytes. Decoding rejects truncation, trailing
streams and expansion above 1 MiB. All original provenance and member hashes
survive; exceeding a bound stops instead of truncating evidence. Larger cache
member catalogs use separate generation/hash-pinned objects: at most 256 KiB
encoded and 4 MiB decoded. Catalog writes/reads are charged to the same slot. Contiguous selected members from the same exact
generation share one bounded range read; gaps are never fetched. Each member
still receives its own SHA256 check before the destination is published.
Read counts and the extra bounded-reader probe byte are checked before I/O.

`priorAttemptCounts` carries previous attempts into the two-attempt limit.
Claims remain immutable and nonrefundable, including ambiguous failures. A
new plan is not permission to reset previous campaign usage. The offline
forecaster checks category totals, source/rescue allocations, operation bounds,
recomputed costs and the absence of approval/dispatch flags.

The changed adapter passed 21 affected regression tests; 19 focused compact
record/forecast/range tests passed, followed by one targeted check of the added
cumulative-envelope assertions. Twenty saved real job receipts round-trip
without losing a field: 105,469 plain bytes become 32,315 encoded bytes;
largest encoded record 2,949 bytes. No imagery was rendered for this check.

## Full dependency and cache model

The offline graph contains 34,750 logical jobs, 278,278 raster tiles and 27,784
explicit overview dependencies. All 20 completed R4 jobs are excluded from new
work and retain their original recipe/receipt identity. The remaining 34,730
jobs form 2,910 layer/zoom batches of at most 12 jobs. Neighbor DEM candidates
include the existing one-pixel terrain halo. No zoom, quality, extent or layer
is reduced: Hiking/Terrain z10–17, USGS z10–16, optional aerials z10–18, plus
preserved full Sunlight and required private vector/weather dependencies.

Saved cache metadata maps all 8,760 COG blocks (573,865,454 bytes) to known source
identities with remaining regional consumers. This is a candidate selection,
not proof that every block is required for every intersecting job. The original
archives/ledgers remain unchanged. Future cache-hit savings are zero in the
cost model; no full projected 526 GiB transfer is required or assumed.

## Unapproved capacity envelope

| Incremental retained category | Hard proposed cap |
|---|---:|
| Raster/shared checkpoint payloads | 8 GiB |
| Delivery package objects | 8 GiB |
| Cumulative selected source-cache objects | 5 GiB |
| Orphan/retry payloads | 2 GiB |
| All claims, receipts, catalogs and indexes | 1 GiB |
| Total | 24 GiB |

The 5 GiB cache cap includes the existing selected bytes; it is cumulative, not
a rolling cache that assumes deletion. Sixty-four finite rescue jobs replace
an assumed full second regional attempt. Across 5,884 primary/recovery/rescue
slots, worst reserved bookkeeping is 959,004,672 bytes (0.893 GiB), including
16 KiB per job receipt, 512 cache catalogs and 128 MiB general index allowance.
Legacy claim/final reservations alone would consume 11.492 GiB for those slots.

The inherited mean archive projection is 7,685,212,160 bytes (7.157 GiB); the
sum of upper sample-spread estimates is 8,486,559,278 bytes (7.904 GiB), within
the 8 GiB per-copy quota. Neither figure is a statistical upper bound. Larger
real outputs stop processing; they do not authorize quality reductions.

The read allowance is 21 GiB: 8 GiB checkpoint assembly, 8 GiB final package
verification, 1 GiB overview children, 1 GiB selected-cache recovery, and 3 GiB
metadata/receipts/catalogs/recovery. Allow at most 90,000 Class A and 150,000
Class B operations. The structural model allocates 82,892 A and 114,344 B;
extra fragmentation, probes or retries consume remaining capacity and stop at
the hard limit. No unmetered full restore is included.

Conservative planning rates remain $0.03/GiB-month, $0.23/GiB read, $0.01/1,000 A
and $0.001/1,000 B, with 20% contingency and no trial-credit deduction. The
complete capped first-month model is $6.60 gross / **$7.92 with contingency**;
24 GiB continuing storage is **$0.864/month with contingency**. These are
incremental producer estimates, not current account invoices. The proposed
$8 initial and $1/month allowances are still unapproved. Stopping compute does
not stop retained-storage charges; no lifecycle or deletion is assumed.

## Next bounded stage and remaining evidence

The private plan names twelve unfinished jobs: two adjacent source windows for
each of five raster layers, plus two overviews whose children already exist in
R4. Its explicit reusable selection is 4,457 blocks / 292,093,952 bytes. Contiguous packing needs five bounded
range reads rather than 4,457, with zero overfetch and every member hash retained.
This is an exact metadata layout result, not another live recovery test. It also
requires measured intake of the accepted 13 vector layers and weather members.
Proposed limits: 1 GiB stored, 1 GiB read, 200 A / 500 B, 2 GiB official-source
transfer, 2,000 source requests, twelve attempts, three hours and one worker.
The conservative first-month cap estimate is $0.315; propose reserving $0.35
within the campaign allowance, not in addition to it. Continuing storage at
that stage's cap is $0.036/month including contingency.

This is a planning artifact, not an executable production authorization. The
exact source snapshot, private cache handoff and generation-pinned dependency
references must be bound in the next restricted workflow. Inspect the new
compact record in the same bounded production/recovery stage; do not repeat
passing iOS CI, old benchmarks, IAM investigations or the separate drill.

Topology, cache identity matching and quota/cost arithmetic are validated.
Exact regional COG range demand, source/time quota sufficiency, regional pixel
coverage and accepted private-input sizes cannot be proven from the saved
sample evidence. The 704 GiB primary + 16 GiB rescue source allocations are
quota slices, not measurements; the inherited 526 GiB / 473-hour projection is
unchanged. The complete pipeline still needs dependency recovery/workflow
sequencing integration and an evidence-based reconciliation after the bounded
stage. Therefore full-Gorge production remains HOLD even if funding is later
approved. No per-batch owner supervision or new IAM/deployment is required.
