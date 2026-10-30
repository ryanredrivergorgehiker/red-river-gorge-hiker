# Offline regional scaling assessment

This change adds read-only evidence analysis. It does not alter the production
controller, image recipes, accepted packages, identities, budgets or workflows.

The second bounded stage remains accepted: 44 cumulative jobs, 436 raster tiles
and 320 Sunlight assets. Conditional third-stage authority does not release funds
until both capacity/cache admission and useful scaling evidence pass. The
original third candidate fails that gate; its only new COG is a DEM and it
reuses the same leaf-off source and all-cache persistence path.

## What was resolved

- The $7.92 model is an allocation of 24 GiB storage, 21 GiB reads, 90,000 Class A
  and 150,000 Class B requests, including 20% contingency. It is not a forecast
  derived from unique regional source ranges.
- That allocation permits 5 GiB cache storage but only 1 GiB cache recovery.
  Independently reading all 5 GiB instead raises the same model to $9.024.
- The current small-stage path restores all shared inputs for each batch and
  persists/recoveries all new raw cache ranges. Repeating it is inconsistent
  with the regional model. Larger batches alone do not solve cumulative storage.
- The exact previously passing native source removes verified transport TARs
  and shares immutable parts across active/pending/rollback. Its limits remain
  256,000,000 bytes and 60,000 members per part, 64 parts per group.
- Full-grid metadata partitioning preserves all 278,278 tile coordinates and
  the quality profiles. Compression scenarios remain estimates, not pixels or
  complete packages. Physical installation size is not claimed.

## Tools and reproducibility

`cached_tiff_analysis.py` reads only supplied existing cache blocks, checking
each block against its saved SQLite SHA-256 and length. Missing metadata fails
without network fallback. It parses TIFF/BigTIFF dimensions, offset/count arrays
and georeference tags. All-level, full-tile-halo bounds quantify possible source
reuse; they deliberately are not predicted GDAL transfer amounts.

`assess_gorge_regional_scaling.py --workspace PATH --output PATH` consumes the
established evidence layout (`stage6/forecast`, `stage6/evidence`, earlier
benchmark receipts, and `stage7/evidence/PRESERVED-TIFF-LOCALITY.json`). Add this
scripts directory and the established benchmark scripts/dependencies to
PYTHONPATH. No source URL is opened, no raster is rendered, and no dispatch
function exists. The result includes exact input hashes, conditional no-go,
source-boundary statistics, batching comparisons, cost reconciliation, full-grid
package simulations and a replacement proposal with spending disabled.

The private report and evidence are authoritative for measured results and
preserved checkpoint references; those private inputs are not stored in Git.
Ten new focused tests cover budget inversion, cumulative ceilings, historical
release preservation, source-incidence counting, missing/corrupt cache data,
TIFF bounds and source-range unions. Existing CI and benchmarks are not rerun.

## Credible path, still requiring validation

1. Reuse accepted shared proof; fetch full shared payload for core assembly,
   not every raster worker. Preserve the original shared files and proofs.
2. Retain spatial locality within source families. Naive source-ID sorting can
   increase the number of source/batch crossings for aerials.
3. Validate a prospective selective-cache policy for future data. Never delete
   or rewrite existing caches. Pinned official-source refetch for any future
   transient data needs measured bounds and tested failure behavior.
4. Use independent output recovery to perform package assembly in the same
   read, then verify final package hashes. Do not count a second assembly read
   as free.
5. Compact repeated provenance into immutable source catalogs referenced by
   job receipts; enforce measured metadata and operation budgets.

The $7.218 future / $7.918 including the two historical $0.35 releases scenario
is an admission target, not a new validated forecast or authorization. It
requires 22 GiB future storage, 19.5 GiB reads, 75,000 A and 120,000 B operations,
including 20% contingency, and no more than 0.5 GiB future durable raw-cache
growth. Those conditions are unproven. Regional production remains disabled.

The replacement proposal surveys missing regional source headers first, then
admits two diverse source-boundary windows and two already-unblocked overview
jobs only if all existing bounded resource ceilings fit. It needs separate
approval because its exact jobs differ from the conditionally approved set.
No additional funds were released during this offline assessment.
