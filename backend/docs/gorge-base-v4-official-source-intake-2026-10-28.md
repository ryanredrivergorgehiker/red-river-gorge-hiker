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
