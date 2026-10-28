# Prepared offline map production — revision 3

The approved architecture remains public government source -> private verified
packages -> existing private GCS -> existing authenticated Base package delivery.
No command here publishes a catalog, uploads protected data, dispatches Actions,
changes entitlements, deploys, or raises a billing budget.

Core: Hiking/KyTopo z10–17, USGS Topo z10–16, Terrain z10–17, full accepted
Sunlight, the 13 established vector families and existing weather snapshot.
Optional independent groups: Kentucky 2022 NAIP leaf-on z10–18 and official
KyFromAbove leaf-off z10–18. All three groups are required product capabilities.
USGS z17/18 must never be synthesized or silently substituted.

`orchestrate_gorge_region.make_plan(inventory, limits)` creates all 34,750 jobs
for 278,278 final raster positions. Inventory contains `sources` arrays for
`hiking`, `dem`, `leaf-on`, and `leaf-off`, with immutable IDs, official URLs,
WGS84 footprints and metadata hashes. Bounds/footprints are planning evidence;
source masks, grid, dimensions, complete XYZ sets and file hashes are independent
acceptance checks. Runtime and processing code are pinned into the plan.

Limits require explicit cumulative attempts, reserved seconds, output bytes and
child seconds. The current engineering plan permits only 12 attempts, 3,600
reserved seconds, 500 MB outputs, and 300 seconds per child. Defaults execute
zero jobs. Native workers consume a single durable reservation and cannot be
restarted using the same reservation. Crash reservations remain charged. Two
attempts per job are allowed across resumes; failed work stops for inspection.
Maximum invocation is 12 jobs. No uncapped mode exists. Full production needs a
separate measured plan and existing spending-control verification.

Example bounded resume (all paths private, outside this source checkout):

```sh
python backend/scripts/orchestrate_gorge_region.py \
  --plan /private/REGION-PLAN.json --output /private/region \
  --cog-cache /private/existing-cog-cache \
  --service-cache /private/existing-service-cache \
  --max-jobs 1 --live-source
```

COG cache remains capped at 250 MB and the NAIP/USGS cache at 80 MB/120 requests.
Those old ledgers are never reset. They are engineering limits, insufficient for
an unrestricted full build. A subsequent reviewed production source ledger must
have measured limits; modifying these values is not an approval to spend money.

`extend_gorge_sunlight.py` preserves the accepted 30 sectors and extends to 80
using the exact hard-rim implementation, 2.5 m accepted processing grid, 180 m
halo and 1,100 ft threshold. The accepted ZMeters export is already meters:
335.28 m threshold; never multiply these values by the foot conversion again.
Original DEM COGs independently use their established per-source vertical unit.
The separate extension source ledger is capped at 1 GB / 101 requests.
`validate_gorge_shared.validate_sun` verifies completed extension assets without
regeneration or another elevation download. Completed measurement receipts retain
the exact executed source snapshot; harmless fetched trailing-newline differences
are reconciled to repository blob hashes separately, never concealed as rerenders.

`prepare_gorge_shared.py` consumes a hash-verified extracted accepted native
package and full-region Sunlight. It retains established vectors/weather, excludes
legacy low-quality regional rasters, and produces the descriptor required by the
native multipart renderer. The accepted private native package is still needed
as input; placeholder dependencies never satisfy regional validation.

`build_gorge_map_bundles.py --scope regional` requires complete coordinates and
shared-content validation. Benchmark packages cannot activate. Immutable parts
are at most 256 MB / 60,000 entries, at most 64 parts per group. Both index and
parts get inactive private-GCS catalog candidates, using the existing Base
entitlement and independently authorized backend transfer. Bucket/object/catalog
activation remains a separate existing controlled release operation.

Native installation authenticates the index, reauthorizes every part (including
local reuse), checkpoints 8 MiB ranges, rejects redirects and inconsistent range
headers, verifies archive/manifest/member hashes, and atomically switches one
active group pointer only after complete verification. Extracted content-addressed
parts are shared between active, pending and rollback groups. Transport archives
are deleted after extraction; unchanged parts incur no new download/extraction.
One part/index checkpoint per group bounds abandoned transport storage. A corrupt
optional group does not hide verified core; repair, removal and rollback are
independent. Core corruption fails closed and exposes rollback recovery.

Native source and five added XCTest cases still require Xcode compile/execution.
Local Python/backend tests are not represented as native acceptance or physical
iPhone measurements. `forecast_gorge_bundle_storage.py` distinguishes logical
file bytes from APFS allocation, retained rollback, pending updates and OS reserve.
