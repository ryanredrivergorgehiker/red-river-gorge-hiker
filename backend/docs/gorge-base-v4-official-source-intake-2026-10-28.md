# RRGH Gorge Base v4 — official offline imagery intake (2026-10-28)

Status: **SOURCE INVENTORY / PRIVATE QA ONLY — NOT A BUILD, NOT A SIGNED PACKAGE, NOT APPROVED FIELD MAPS.**

## Evidence retained
- Kentucky GIS county tile-package map service: https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_County_TilePackages_WGS84WM/MapServer/0
- Kentucky program imagery/distribution: https://kyfromabove.ky.gov/ — statewide base imagery/elevation data generally public domain, attribution recommended; review product-specific conditions, including base-map composition
- Official public-domain data registry: https://registry.opendata.aws/kyfromabove/
- Google Drive official source discovery ZIP (16 direct county links; eight intersecting counties): https://drive.google.com/file/d/1KRFMsF3OwGJlN1P420GedmpTG83HKW1R/view
- Google Drive metadata-only HEAD/byte-range proof ZIP: https://drive.google.com/file/d/1Vbac5eXoR0Z7enaj5fXdvVYfW4Hu3hED/view
- Metadata-only GitHub Actions succeeded; 14/16 sources support HTTP 206 byte-range reads. The 14 known-size county packages total **200,086,949,343 bytes** (~200 GB). Two size probes timed out. Downloading all archives is NOT an acceptable workflow.

## Actual official source description (do not rename)
The MapServer county records identify **TCM_Base** and **KyFromAbove 2019 six-inch leaf-off** county TPKX files. TCM_Base is a *base map*; its metadata DOES NOT demonstrate that it is the detailed Kentucky topo layer. The leaf-off package may serve the `leaf-off-aerial` native raster role after quality, version, licensing, and actual XYZ coverage are checked. Neither category establishes the required `kentucky-topo`, `usgs-topo`, `terrain-relief`, or `leaf-on-aerial` package content.

Intersections returned for bbox [-83.80, 37.65, -83.40, 37.95]: Breathitt, Estill, Lee, Menifee, Montgomery, Morgan, Powell, Wolfe. Some county packages may contribute no tiles to the final clipped rectangle; only an exact XYZ coverage audit can establish which are actually required.

## Implemented engineering
- `discover_official_ky_county_sources.py`: query the official feature service for intersecting county **metadata only**, no imagery copies and no use-right assumptions.
- `probe_official_ky_tpkx_metadata.py`: bounded HEAD/single-byte Range probe, with source link allowlist, no full downloads; upload metadata artifact.
- `http_range_zip.py`: seekable HTTP 206 Zip reader with requested-range verification, ETag/size checks, small LRU cache, max transfer budget, and HTTP 200 full-download refusal.
- `import_official_tpkx_xyz.py`: import only actual, original 256px imagery from local or bounded-range TPKX Compact Cache V2 into canonical local XYZ. Enforces true Web Mercator origin and LOD resolutions, rejects missing/invalid tile locations, conflicting overlaps, and absent source provenance.
- Synthetic tests: `test_discover_official_ky_county_sources.py`, `test_probe_official_ky_tpkx_metadata.py`, `test_http_range_zip.py`, and `test_import_official_tpkx_xyz.py`.
- Bounded Powell County leaf-off pilot in backend CI is a **nonproduction single-scale source test**, restricted to a tiny Geographic bbox and 60 MB transfer ceiling; its result cannot prove Gorge-wide or field-ready map coverage.

## Still blocked / next actual-source work
1. Confirm **real** Powell leaf-off pilot yields original imagery and exact coordinates with under-budget HTTP range reads; retain bytes/hash and source metadata.
2. Obtain the other four required correct source classes: Kentucky detailed topography, USGS topography, actual terrain-relief DEM/hillshade, and genuine leaf-on aerial. USGS National Map and Kentucky KyFromAbove raw/STAC data are candidate sources; not substitutes without verified imagery.
3. Import each layer at required minimum through max detail; reject absence, blurred upscaling or invented geometry; check license+attribution per source.
4. Measure actual data size against the existing bounded 1.5 GB v4 TAR package and available iPhone capacity. Prepare a *new* immutable source version, never overwrite deployed v3.
5. Nonprod backend signed catalog and protected lease authorization, then full physical iPhone offline Base + two Day Hikes install and disconnected cold-restart QA. Existing owner Gate A remains REJECTED until this is demonstrated.

No new third-party subscription, licensing fee, protected field use, map-data deployment, sales, or verified expense has been made in this source-intake work.


## First real original-resolution leaf-off tile verified (October 28, 2026)

A strict nonproduction test on the actual publicly downloadable Powell County KyFromAbove 2019 six-inch leaf-off TPKX (`zi0ltrlzlx39ashp232dt37cdj0utem1.tpkx`, 14,845,388,076 bytes) produced exactly one valid, original PNG image:
- XYZ `leaf-off-aerial/13/2191/3166.png`, 256 x 256 RGBA, 122,687 bytes.
- SHA-256 `ad1de71fe82643ce3a2a519ff306cb9f93c1b52214ebf80bc70a3175eb8b3708`.
- Micro-bounds [-83.689,37.773,-83.685,37.777]; representative imagery has real pixel variation and was not stretched from the former v3 regional raster.
- Initial ZIP bundle reader transferred 3,319,085 bytes, rather than the full 14.85 GB. Official CompactV2 bundle exposed `version=3, declared_count=0` (contrary to Esri's published normative 16,384 count), while preserving full 131,072-byte index and valid per-tile images. Parser accepts only count 0 or 16,384 with all other version, offsets, sizes and image constraints intact. Dedicated synthetic test added.
- Actual county bundle `tile/L13/R0c00C0880.bundle` has ZIP method **0 (STORED)**, compressed/uncompressed size 2,465,616 bytes.
- Implemented and independently synthetic-tested direct CompactV2 tile-offset range extraction from ZIP_STORED entries, using the existing bounded HTTP206 source reader. Repeat real public Powell pilot yielded the **same exact PNG SHA** but only **1,221,933 bytes transferred**. No coordinate reconstruction, image resampling or full county download.
- Stored tiny verified test package in private operational Google Drive: https://drive.google.com/file/d/1aqYZIshGrFnkfiU8ocsnweVgFLtDZHS4/view (source QA only, NOT full Base).
- Real official file, exact SHA, bounds and delta demonstrate one correct source/scale pipeline. **This is not an installed v4 package and cannot establish complete Gorge-wide coverage or other four map layers.**
- GitHub Actions delivery-contract and synthetic selector tests pass on source after changes; independent old v3 high-resolution GeoTIFF preflight is still failing its upstream remote source. Never merge v4 draft into automatic deploy or sign new Base from this pilot.

Remaining hard blockers: legally vetted all-five-layer z10–16 closed tile coverage, actual volume fitting 1.5GB uncompressed offline budget, signed UID-bound Base+two Day Hikes downloaded and verified, native hard-offline iPhone rendering and owner acceptance. No new revenue, external purchase or billed map service.


## Confirmed real high-zoom KyFromAbove source — 2026-10-28

Real official Powell County KyFromAbove 2019 six-inch leaf-off TPKX, original file **14,845,388,076 bytes**. Nonproduction selective-read real QA produced **7 original 256px tiles** at z13–16 in a tiny approved testing bbox [-83.689,37.773,-83.685,37.777]. All seven images and source metadata saved privately in Drive:
https://drive.google.com/file/d/1kOMgvwoTgX3_aGUCloW6LKmCbjNY1KoP/view

Actual tile distribution: z13 = 1 PNG; z14 = 1 JPEG; z15 = 1 JPEG; z16 = 4 JPEG. Total network bytes read **4,367,661**, rather than 14.85GB full source. Exact original z13 tile SHA **ad1de71fe82643ce3a2a519ff306cb9f93c1b52214ebf80bc70a3175eb8b3708** preserved from single-zoom pilot. Higher-zoom JPEG pixels are source-original with per-image SHA recorded; no GIS reconstruction, stretching, upsampling or compression was performed.

Engineering confirmed one real Kentucky source varies image encoding by zoom, contradicting earlier uniform file-format assumption. Schema4 builder and iOS validator now allow **tileFormat = mixed** with per-tile canonical `tiles/<raster-id>/<z>/<x>/<y>.<png|jpg|jpeg>`, preserving exact source bytes and full SHA integrity, rejecting duplicate/conflicting formats for one XYZ coordinate. The MapKit local tile reader already loads both image types. Matching Python/Swift regression tests added. Source changes remain UNMERGED and were not proven by owner device as of note.

The official TPKX uses Esri CompactV2 version3 but zero declared header record count (full index is present). Source parser permits that observed official header only if all other fixed index, offset and image bounds checks pass. ZIP entry method is **STORED**, enabling a direct local-header + index + individual tile-offset HTTP206 range reader. Repeated real z13 image hash matched while network transfer fell from 3,319,085 to 1,221,933 bytes. Full z13–16 seven-image sample transferred only 4,367,661 bytes. No whole-county archive downloaded.

**Not released**: this isolated seven-tile QA sample is not even a complete leaf-off layer, and does not establish topo, terrain, leaf-on or all published Day Hikes. Real authenticated nonprod v4 packaged/download/airplane-mode client and owner acceptance remain blocked. Old production/nonproduction v3 immutable archive preserved, no purchases.


## Continued source engineering: October 28 owner budget authorization and COG discovery

**Owner budget direction:** The October GitHub Actions account budget was visibly increased to **$350**, with **$275 reported spent / 78%** when the owner supplied the billing screenshot on October 28. Earlier $250 stop-threshold notes are superseded for remaining October development runs; **do not exceed the $350 account-level ceiling**. The screen is a usage-budget observation, **not a verified paid invoice or bookkeeping expense**.

**Private CI operating-cost improvement:** On draft backend PR #68 only, cancel superseded backend delivery workflow runs and skip the separate known-failing legacy v3 *real-source* rebuild (55-minute job). The existing v3 real-source gate remains intact for other backend PRs. The candidate branch cannot deploy nonproduction or overwrite v3. The standard delivery-contract/emulator and synthetic v4 source checks still execute.

**Source registry and rights, source-specific rather than inferred from map-service tiles:**

| Required offline visual | Highest-value official candidate | Current rights/coverage status |
| --- | --- | --- |
| Kentucky topo | KyFromAbove **KyTopo Map Series** individual COG GeoTIFFs under public S3 `elevation/KyTopoMapSeries/`; released May 2026 | Kentucky public-domain data-with-attribution claim documented; actual quadrangle/Gorge coverage, source rendition and reuse evidence still unverified |
| USGS topo | USGS The National Map current US Topo GeoTIFF or approved raw public-domain style/data | USGS maps generally public domain but earlier maps may include identified commercial road exceptions; verify selected product's embedded credit/metadata |
| Terrain relief | KyFromAbove public LiDAR-derived DEM COGs `elevation/DEM/` or USGS 3DEP (public-domain) | Need exact DEM geolocation/scale/extent, terrain derivation, per-source attribution and genuine near zoom |
| Leaf-on aerial | **USDA NAIP** growing-season orthophotos, with Kentucky's official 2022 NAIP 60-cm statewide reference | This is the *correct seasonal class*; do not mislabel Kentucky's leaf-OFF KyFromAbove TPKX. USDA raw public-domain data, locate source acquisition and license/metadata before original TIFF/COG import |
| Leaf-off aerial | Existing official KyFromAbove Phase 2 2019 six-inch TPKX, and Phase 2/3 orthophoto COGs in `imagery/orthos/` | Actual 7 original Powell z13–16 source tiles verified; full eight-county Gorge clipped coverage **not** yet verified |

Official source references:
- Kentucky public program and catalog: https://kyfromabove.ky.gov/
- AWS Open Data Kentucky COG registry, public domain with attribution: https://registry.opendata.aws/kyfromabove/
- Kentucky government STAC endpoint: https://spved5ihrl.execute-api.us-west-2.amazonaws.com/
- Kentucky 2022 NAIP 60cm leaf-on reference: https://opengisdata.ky.gov/maps/kygeonet%3A%3Akentucky-2022-naip-imagery-tile-layer/about?layer=0
- USDA NAIP public-domain imagery metadata: https://catalog.data.gov/dataset/national-agriculture-imagery-program-naip-imagery
- USGS The National Map: https://www.usgs.gov/tools/download-data-maps-national-map
- Official KyFromAbove data distribution policy: https://kygeonet.ky.gov/kyfromabove/pdfs/KyFromAboveDistributionPolicy.pdf

**New metadata-only STAC stage:** `discover_kyfromabove_stac.py` searches a strictly Gorge-bounded box, only two recognized DEM/orthophoto collections and at most three candidate records per collection. HTTPS official endpoint and response-byte limits are enforced, other external URLs are rejected, raw COG bytes are never retrieved, and missing KyTopo/USGS/leaf-on roles remain explicitly unproven. Network-free tests cover bounds, limited cardinality, provenance and invalid external assets. The CI-produced metadata artifact is a short-lived provenance/intake aid, **not a public multi-gigabyte Base package**.

**Intake progression, no simulated coverage:** identify actual intersecting COG/TPKX assets; verify WGS84/GIS coordinates, original resolution, exact coverage and written reuse conditions; produce clipped *derived* XYZ rendering without invented detail, clearly distinguished from native source-image bytes; run all five independent layer coverage and storage-budget audits; then build a separate immutable schema4 version. The existing 1.5 GB uncompressed TAR / 60,000-file guard is mandatory. The old ~200GB of county archive sizes does not imply that many bytes are required for a bounded Gorge output. No real package or device acceptance yet.
