# Expanded source production and rollback

Owner approved implementation on November 2, 2026, including isolated development,
preserving other branches, continued production and a quick rollback path.

## Preserved working checkpoint

- Controller: `fc09347ca84d736fb6ff73568c833ad77865542f`, retained on
  `lane20/rollback-before-expanded-source-20261102`.
- Production source: `244cd9f30eb4eeb03e7a516ecc27e3be8991e3f8`, retained on
  `lane20/source-checkpoint-before-expansion-20261102`.
- Control digest: `638bd49d382454bc82b73969bd6cba813c52ce575409499fa62ee79f8df0eb98`.
- Wave 97 independent recovery: run 41525016404, 11,512 accepted jobs,
  120,002 raster tiles and 320 Sunlight assets. Receipt generation
  1793653655957034, SHA256
  `a6e998204b06a9d8cf1e736a39abe43dbab9bd8719536ead49a4d44929d22a22`.

These are rollback references, never instructions to restore historical counters,
replay Wave 98 or replace newer accepted map data.

## Source integration

The exact preserved catalog expands source candidates to nine KyTopo quadrangles,
558 DEM objects and 558 ortho objects. Every original source record remains
byte-equivalent. New source objects require attribution and native EPSG:3089,
resolution and vertical-unit verification. Existing ETag/If-Match source pinning,
complete native pixel masks, seam evidence, output hashes, source allowances and
fresh-runner package readback remain mandatory. Bounding boxes do not certify pixels.

Initial mixed batches contain at most three Hiking, three Terrain and three leaf-off
jobs. Nine 600-second reservations fit inside the actual 9000-second producer slot.
No job retry allowance, Cloud identity, role, bucket, resource ceiling, website,
app interface or independent development branch is changed.

## Recovery-boundary controller upgrade

Test before enabling. At deployment, atomically add a pending upgrade containing
the exact old and new controller digests to the current state together with the
reviewed code. Leave the active digest, run, source, plan and receipt untouched.
The old checked-out run completes using its original digest. The next exact
dispatch claim may switch to the preauthorized new digest once, preserving the
same source plan. That run's subsequent fresh plan introduces expanded sources.
Wrong digests, unapproved upgrade, mismatched inputs or moved source lease fail
without claiming or consuming Cloud work.

## Fast source-policy rollback

Compare-and-swap only `sourcePolicyMode` to `legacy` in the CURRENT owner state.
Do not replace state with this checkpoint. The active producer and recovery finish;
the next plan selects from its preserved `legacyInventory`, using current completed
IDs, quarantines, cumulative ledgers and exact predecessor receipt. The new native
validation renderer is backward-compatible with original sources. Expanded accepted
tiles remain protected. Setting `sourcePolicyMode` back to `expanded` prospectively
restores the reviewed catalog. When legacy territory is exhausted, do not invent
work or replay slots; keep engineering on a corrected prospective source policy.

A full code rollback also requires a fresh reviewed digest transition at a safe
boundary. Never force-reset the moving production branches. Unrelated code stays
on its existing branches.

## Remaining product work

This rollout does not certify complete geography, all source pixels, overviews,
final Core/optional package manifests, authenticated delivery or physical iPhone
acceptance. Those remain execution tasks after source integration. Preserved
quarantines require separately reviewed fresh source-bound recovery; they are not
silently reset or included as completed tiles.
