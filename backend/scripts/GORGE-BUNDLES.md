# Kentucky leaf-on, USGS Topo and separate offline bundles

Continues `c5fbcbdbc4aa9846dac99f0d75b8f57dea7caf04`. This source-only engineering
change preserves private GCS, the authenticated backend and the existing Base grant.
It adds no Actions workflow, production command, deployment or entitlement.

## Bounded source benchmark

The official Kentucky `Ky_NAIP_2022_2FT/ImageServer` is publicly readable. Its
four-band 2-foot service is a genuine growing-season NAIP source. Lossless TIFF
`exportImage` works even though `exportTilesAllowed` is false. Native-grid exports
are derivative service responses, not downloaded original TIFF masters. Keep all
four source bands in the private cache; RGB display derivatives use JPEG 90 with
no chroma subsampling. Never require EarthExplorer sign-in for this working path.

USGS `USGSTopo/MapServer` is cached cartography. Acquire each zoom independently
and preserve official PNG/JPEG bytes. Metadata lists levels through 23, but its
max scale is z16 and all 60 sampled z17/18 tiles returned 404. Do not fabricate
higher zooms or classify transport/authentication errors as missing imagery.

```bash
python backend/scripts/benchmark_ky_naip_usgs.py \
  --plan /private/old-benchmark/PLAN.json \
  --output /private/service-benchmark --cache /private/service-cache \
  --live-source-benchmark

python backend/scripts/build_gorge_map_bundles.py \
  --benchmark /private/old-benchmark --benchmark /private/service-benchmark \
  --accepted-sunlight /private/verified-shared \
  --provenance /private/package-provenance.json \
  --output /private/separate-packages --release 2026.10.28.benchmark2

python backend/scripts/forecast_gorge_map_bundles.py \
  --original-benchmark /private/old-benchmark \
  --service-benchmark /private/service-benchmark \
  --source-ledger /private/source-ledger-groups.json \
  --service-cache /private/service-cache/requests.sqlite \
  --output /private/complete-forecast.json
```

Service benchmark ceiling is 80,000,000 reserved bytes / 120 requests, max 8 MB
per response, one process lock, persistent reservations and SHA-256 cache checks.
A source 404 is pinned so a restart does not spend requests on absent levels.
At most three Gorge windows are allowed. Overview tiles are deduplicated across
windows. Receipt/recipe mismatch fails closed; use a new output root after code
changes and reuse the cache. The older original-COG cache and its 250 MB cumulative
ceiling remain separate and unchanged. Do not reset either ledger on resume.

## Package profiles and limits

Target bounds: [-83.80, 37.65, -83.40, 37.95], z10 regional overview through:

| Group | Contents | Maximum zoom |
| --- | --- | --- |
| Required core | Hiking/KyTopo, USGS Topo, Terrain, accepted Sunlight/shared content | 17 / 16 / 17; Sunlight independent |
| Optional leaf-on | Kentucky 2022 NAIP | 18 |
| Optional leaf-off | Kentucky Phase 3 leaf-off aerial | 18 |

Each plain USTAR part is at most 256,000,000 bytes and 60,000 members; each group
has at most 64 parts. No native 1.5 GB / 60,000-entry safety limit is raised.
Exact TAR padding is checked. Stable layer/zoom/64x64 spatial boundaries avoid
repacking every region when one earlier tile changes. Full-hash identities allow
unchanged parts to be reused across release indexes. Indexes and parts are
immutable, source hashes are checked before build, and archive content is read
back after writing. Per-part receipts allow interrupted/resumed builds to rehash
completed archives without repacking; a producer lock prevents concurrent writers. The complete five-family byte forecast enumerates coordinates
and synthetic mean sizes only; it does not generate or validate regional imagery.

Every candidate includes ten-field source provenance. Part catalog candidates use
existing `offline_base`/`base`, `offlineManifest`, `storageBucket`, `objectName`
and the backend's `rrgh-sha256`, `rrgh-package-id`, `rrgh-version` metadata keys.
The bucket is deliberately unset and candidates are inactive/contentReady=false.
There is no upload or catalog publication action here. Source/output/cache bytes
and operational evidence must remain out of this public code repository.

## Integration status and acceptance gates

**These are benchmark packages, not an installable field release.** The existing
native schema-4 monolith cannot consume these indexes. The iOS companion source
adds strict bundle descriptor validation and safe same-volume staging consumption;
it does not yet implement bundle downloading, atomic multi-part activation,
composite tile mounting, optional UI or reference-counted rollback cleanup.
The eventual index itself must be authenticated by the existing delivery path,
and every part descriptor must match independent backend authorization.

`--scope regional` requires exact complete XYZ coverage. Required core also fails
closed pending an independently accepted full-extent shared-content receipt.
The accepted Sunlight assets cover a smaller extent; they are not relabeled as
full-region coverage. Keep route/vector/weather and hard-rim Sunlight acceptance
requirements. Aerial sample coverage, footprint union or green canopy alone is
not full pixel, seam, alignment or navigation QA. z10 is this proposed bundle
contract's overview minimum; the existing schema-4 z8 requirement remains unchanged
until a compatible bundle renderer is implemented and validated.

Forecasts separate measured archive bytes from projected regional/device bytes.
An archive A plus extracted E remains A+E installed. Safe same-volume staging
consumption removes the duplicate A during extraction; cross-volume callers retain
the copy fallback. Keep all verification, account-generation fences and one prior
verified generation. Physical iPhone allocation and download timing require native
execution; Python timing is not a GitHub runner measurement.

Paid jobs remain blocked until current spend, the $350 stop control and the
incremental $10 limit can be verified. No budget change or full production follows
from a forecast. Current GCS location/access/retention and native QA remain gates.
