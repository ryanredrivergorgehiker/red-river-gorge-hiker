# Gate C: one released 12-job stage

This coordinator binds the existing $0.35 release to exactly the twelve approved unfinished jobs. The $7.65 campaign balance remains locked. It is not a full-region dispatcher and cannot deploy or replace packages.

The complete source snapshot, regional inventory, completed dependencies, job identities, allowance and finite immutable checkpoint slots are checked before cloud execution. The new bootstrap input proof is anchored to a generation-pinned immutable bootstrap receipt; this avoids changing the funded plan namespace after cloud input generations become known. No slot can be reclaimed and workflow reruns are rejected.

## Allocation within the existing owner ceilings

| Slot | New storage MiB | GCS response/read MiB | Class A | Class B | Attempts | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| Bootstrap | 350 | 500 | 64 | 16 | 0 | 600 |
| Production | 600 | 8 | 110 | 356 | 12 | 9000 |
| Fresh recovery | 74 | 516 | 26 | 128 | 0 | 1200 |
| Total | 1024 | 1024 | 200 | 500 | 12 | 10800 |

Official-source ceilings remain 2 GiB and 2,000 requests. One worker, one invocation, no retries beyond the native uploader's prepaid status recovery. Worst-case funded Cloud Storage model remains $0.315 with 20% contingency inside the $0.35 reservation; continuing storage at this stage ceiling is $0.036/month including contingency, within the approved $1/month campaign allowance. These are conservative estimates, not current billing readings.

The measured six-pack bootstrap plus worst-case private input/proof envelope requires 348,053,668 storage bytes, 488,247,531 response/read bytes, 60 Class A HTTP reservations and 10 Class B reservations. The original ZIP is received privately and checked against its fixed 309,600,543-byte SHA256 identity. Its six packed payloads are uploaded by the existing native resumable adapter with complete generation-pinned SHA256 readback; catalogs retain all file extents. No duplicate ZIP object is stored.

Accepted Base is read only from its existing exact version/key. Its full hash, generation and server MD5 precede extraction of the 13 accepted vectors and weather/static references. Legacy rasters are not copied into new products. All previously accepted Sunlight raster bytes are reused unchanged. Missing optional authoring geometry is accepted only when the exact already-accepted raster manifest hash is supplied by the verified seed; the default authoring validator remains strict. Existing manifest and raster hashes are still enforced.

Before every official-source request, the worker reserves cache-growth capacity as well as its source-byte/request allocation. The stage's additional cache-growth sublimit is 320 MiB, encoded output cap is 8 MiB per job, and immutable ledger snapshots total at most 32 MiB. These caps stop work; they never lower imagery resolution or quality. Every completed job is followed by packed new cache members, ledger snapshots and a deterministic output receipt before the next job. Failures retain reservations and attempt cache preservation rather than silently reprocessing.

The second job runs on a fresh runner. It recovers all new cache packs and outputs, validates hashes and exact generations, decodes actual imagery, checks expected tile inventory/grid/alpha and measures adjacent edges including new-to-preserved boundaries. Full-Gorge pixel/seam acceptance, installable package assembly and integrated native acceptance remain later gates.

The transfer descriptor is supplied only through the temporary private RRGH_STAGE_SEED_TRANSFER Actions secret. No payload, signed URL, bearer token, session journal, protected archive, Actions artifact or Actions cache is published. Only sanitized counters, hashes and generation references enter public workflow output. Existing WIF, IAM, bucket settings, Firebase and accepted packages remain unchanged.
