# Resumable original-source Gorge benchmark

Continues the original-source engineering at `e488b70cbd66209c889c6b8e5031b623e4f1ef12`.
The existing private GCS / authenticated backend / signed offline-lease architecture remains the delivery path.
This command is a bounded engineering benchmark, not a production producer or deploy command.

## Run and resume

Use Python 3.12 and `requirements-gorge-benchmark.txt` in an isolated environment.
The private engineering evidence supplies the resolved source plan, source inventories and STAC metadata.
Do not place source rasters, private operational records, protected routes or evidence archives in this repository.

```bash
python backend/scripts/run_gorge_benchmark_batches.py \
  --plan /private/benchmark-plan.json \
  --output /private/benchmark-run \
  --cache /private/original-range-cache \
  --max-jobs 8 --max-source-bytes 250000000 \
  --live-source-benchmark

# Rehash completed outputs without source processing:
python backend/scripts/run_gorge_benchmark_batches.py \
  --plan /private/benchmark-plan.json \
  --output /private/benchmark-run \
  --cache /private/original-range-cache --max-jobs 0

python backend/scripts/measure_gorge_benchmark.py \
  --benchmark /private/benchmark-run --output /private/measurements

python -m pytest -q backend/scripts/test_cached_cog_source.py \
  backend/scripts/test_benchmark_gorge_pipeline.py \
  backend/scripts/test_measure_gorge_benchmark.py \
  backend/scripts/test_run_gorge_benchmark_batches.py
```

Reusing the same plan, recipe, output root and cache validates and skips committed jobs.
An interrupted job can resume with already-downloaded original blocks. Each child processes
one missing job; native process failure gets at most one retry, and normal validation failure stops.
Completed receipts are immutable. Recipe or plan changes require a new output directory;
the pinned original cache can still be reused. The original transfer ceiling cannot be reset
or increased by restarting. Failed and interrupted requests consume their reservations.

## Data and validation

The versioned JSON plan contains the fixed Gorge rectangle, at most 12 named point samples,
and original source records grouped as `hiking`, `dem`, `leaf-off`, and optional `leaf-on`.
Each source has an exact official HTTPS GeoTIFF URL and WGS84 footprint. DEM records must
declare an established `verticalUnit` of `US survey foot` or `metre`; the plan declares
`demElevationUnit: metre-after-per-source-conversion`. Preserve source dates, STAC hashes,
attribution and governing provenance in the private plan. Missing sources remain missing.

The source cache pins URL, length and strong ETag, sends `If-Match` on every uncached range,
requires exact 206/Content-Range/length/ETag responses, and never accepts whole-object fallback.
64 KiB persistent blocks coalesce into at most 2 MiB outbound requests; larger bounded GDAL
reads are assembled locally. SHA-256 is checked on each reused block. One producer owns the
cache. SQLite reserves bytes before network access; atomic writes protect files and receipts.

A z16 ground window is warped once at z18 resolution to generate 1/4/16 XYZ tiles at z16/17/18.
Coverage uses actual source validity masks. Tiles are decoded, dimension-checked and hashed.
RGB uses JPEG quality 90 with no chroma subsampling; Sunlight experiments preserve RGBA PNG.
Terrain and Sunlight share the exact original DEM cache. US survey feet are converted to
metres before invoking the existing 1,100-foot Sunlight Potential algorithm.

The generated Sunlight experiment does **not** include the accepted hard-rim precomposition
and is not a replacement for accepted mobile Sunlight assets. Production must retain the
accepted assets or complete equivalent source/visual acceptance. It is potential, not a
time-of-day shadow model. Hillshade styling is also an unaccepted engineering candidate.
Signal-difference metrics do not prove semantic detail or visual acceptance.

## Output and cost boundaries

`BENCHMARK.json`, receipts, transfer ledger, failure logs, deterministic evidence TARs and
`MEASUREMENTS.json` distinguish measurements from regional extrapolation. Evidence TARs are
explicitly **not installable native packages**. TAR measurements include 512-byte member
padding and 10,240-byte records. iPhone numbers are logical models derived from the existing
archive-retaining installation path; APFS physical allocation requires device measurement.

No Actions workflow, GCS upload, catalog mutation, entitlement change, protected merge or
deployment is introduced. Paid jobs must remain blocked until current account spending,
the $350 monthly stop control, and the incremental $10 cap can be verified. Public standard
GitHub runners have different billing from private or larger runners; do not infer current
account headroom from old screenshots. Keep prepared data private even in a public source repo.

Regional extrapolations are not statistical confidence intervals. Lower zoom byte density
is approximated from z16; unresolved leaf-on, USGS Topo and other inherited assets are not
silently included. The existing schema-4 builder still requires all five raster sets and
enforces 1.5 GB / 60,000 entries. Optional package installation and regional packaging beyond
those limits require further implementation under the same approved architecture.

Full production remains gated on complete source resolution, edge/seam/low-zoom QA,
Sunlight parity, native package integration, private GCS validation, measured delivery/device
checks and a current cost forecast. The bounded engine intentionally cannot launch a full region.

## Kentucky NAIP and separate-package continuation

The public 2022 Kentucky ImageServer and USGS cached cartography are now benchmarked
by the bounded service engine. See [GORGE-BUNDLES.md](GORGE-BUNDLES.md) for the
source clarification, actual z16 USGS ceiling, separate core/aerial producer and
complete-family forecast. Prior evidence and original-source cache remain intact.
