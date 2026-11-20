# Offline completion engineering — 2026-11-02

## Implemented and verified

This change adds local engineering tools outside `backend/scripts`. It does not
change the immutable producer source snapshot, website pages, production
workflows, IAM, Cloud objects, source pins, package contents, or accepted assets.

- `rrgh_required_inventory.py` generates the deterministic required XYZ manifest,
  a SQLite evidence inventory, and a dependency-exact overview queue. Production,
  verification, source coverage, package membership, delivery, and physical device
  acceptance remain separate. Historical receipt-backed acceptance is preserved;
  missing per-tile object/generation/hash evidence is explicitly null.
- `rrgh_source_window_intake.py` binds the reviewed expanded source catalog to
  every z16 window, computes the union of intersecting source bboxes, and identifies
  mosaic requirements. Candidate source metadata cannot authorize production.
- `rrgh_package_readiness.py` checks a normalized private package evidence record
  against the exact required manifest and accepted per-tile bytes. Core requires
  explicit Sunlight, vectors, weather, and shared dependency inventories. Delivery
  and physical iPhone tests bind to the exact package version and hash.
- `rrgh_controller_preflight.py` checks successor lineage, consumed allocations,
  reservations, exclusive cutover evidence, and the two-execution autonomy evidence
  contract. It performs no writes and never authorizes dispatch. This is transition
  groundwork, not an activated or completed autonomous controller.
- `test_rrgh_completion_engineering.py`: 30 new offline tests. The 19 existing
  partial-recovery/source-gap tests and 13 original supervisor tests also pass:
  **62 tests total**. Fixture succession is not live acceptance evidence.

## Fresh evidence and actual-data results

Source branch still pointed to `ec635afb75db606879ac95c7d2730ad899d54bb3` when
read through GitHub. Its Wave058 plan SHA256 is
`982bf03c6053808daeb55929cd33d6ed1f1bf00c11d0de1ba247fbb742b73833`.

The Wave057 producer/recovery logs were freshly retrieved and passed the existing
supervisor verifier. Run [41454631490](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41454631490)
has producer job 125308068642 and recovery job 125310296745. Accepted carry remains
11,144 jobs, **118,130 raster tiles**, and **320 Sunlight assets**. No new production
was launched by this change. The normalized public recovery report in
`evidence/20261102/recovery057-report.json` preserves its origin and immutable
receipt reference; it is not a downloaded raw protected GCS receipt.

The regenerated manifest has **278,278 required positions**, **160,148 not yet
accepted**, and **8,848 missing overview positions**. Manifest stream SHA256:
`bef34f7e982d9651f7e092bbb48b5e48bf4c335060ab905aba2896eb5845945e`.
The governing geographic approval remains unresolved; the spec is explicitly
provisional and does not substitute county outlines for the owner's footprint.

Missing overview positions by zoom: z10 20; z11 45; z12 150; z13 450; z14 1,710;
z15 6,473. The queue identifies 5,629 missing-child cases, 1,770 direct official
USGS reads requiring validation, and 1,449 entries with receipt-backed children.
None is marked production-ready: allocation, renderer/pixel QA, source rights,
resource limits, and authorized initiation still apply. Queue SHA256:
`06a6275628a225f3a76c3ba8198e3fc9fbdc1d8680e2007fbfaa53ebd6f61e62`.

Expanded catalog input comes from PR73 at
`db5abf719445b2fcc52c385f2218653a60b76198`, with exact file SHA256
`fbffbb972a32e6b226519b94370443dc5e47d55759c2a85b55eeb6b993489193`.
The original PR73 metadata audit was rerun successfully and preserved all original
source identities (1 topo, 22 DEM, 22 leaf-off). The stronger union check found:

| Layer | Candidate sources | Full-window metadata coverage | Rectangle-intersection coverage | Mosaic windows |
| --- | ---: | ---: | ---: | ---: |
| Hiking | 9 | 5,180/5,180 | 5,180/5,180 | 474 |
| Terrain | 558 | 5,138/5,180 | 5,180/5,180 | 2,906 |
| Leaf-off | 558 | 5,138/5,180 | 5,180/5,180 | 2,900 |

The 42 incomplete Terrain and 42 incomplete leaf-off full windows are an **edge
treatment issue outside the documented rectangle**, not proof of missing imagery
inside it. Full tile masks/terrain halos still need explicit treatment; never
invent pixels. Source-window evidence stream SHA256:
`06b3cd5ca600399dc2022c76ff64ff8241457561bf618c785e333c1547d7f4bd`.
Bounding boxes are not raster footprints or full pixel coverage. No additional
live pixel reads, source promotion, rights certification, elevation conversion,
package installation, or physical-device tests were performed here.

## Controller activation remains blocked

Current original producer authority is exact `push`, exact repository/owner,
branch `lane20/offline-production-preflight-20261029`, and
`offline-map-producer-access.yml`. The production source also checks this exact
event/workflow in `fetch_gorge_private_seed.py` and
`run_gorge_checkpoint_slot.py`. A trigger-only change cannot fix the handoff.

The previous restricted dispatch attempt failed Google STS authorization. Its
reviewed administrator script already exists at
[upgrade_map_producer_wif_20261031.sh](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/blob/3ceebf6ff15f69b5eb9c678528745792c68d49df/backend/scripts/upgrade_map_producer_wif_20261031.sh).
It adds only the exact same-repository/same-branch restricted dispatch identity,
retains the original push identity, and does not add IAM roles or service accounts.
**It was not applied.** Current live provider policy could not be independently
read here; the source-side rejection is directly verified in current source.

The directive explicitly prohibits identity broadening and bypassing platform
restrictions. This work therefore did not retry the earlier rejected live
workflow-pin mutation or use another route to initiate it. An owner-authorized
identity decision and administrator execution are still required for that proposed
dispatch design. The independent hourly auditor remains an auditor.

The real Wave058 candidate passes local successor/receipt/reservation checks:
20 fresh jobs, modeled worst-case additional Cloud reservation USD0.6456 and
modeled monthly storage admission USD0.8299602834. These are not invoices. The
preflight exits **2**, correctly blocking cutover: no live exclusive ownership,
legacy fence, replacement authentication proof, or current activation observation
exists. Its saved billing snapshot is dated 2026-10-30; the USD350 GitHub hard stop
and current headroom require a fresh observation before activation.

Next controller work after the identity decision: implement the authenticated
dispatcher and source identity guard update on reviewed immutable source; finish
worker-side ownership fencing and durable dispatch deduplication; verify all
entry points and no active producer; fence legacy initiation; run two successive
real independently recovered waves with automatic succession. The preflight is
not a substitute for any of those steps. No two-wave autonomy proof is claimed.

## Reproduce in a checkout with the pinned source commits available

All commands below process local files. Use a new output directory; the tools
refuse to overwrite existing evidence. Keep SQLite inventories, package files,
member hashes, source caches, and private receipt payloads in protected storage.

```bash
python -m unittest discover -s .github/automation -p 'test_rrgh_*.py' -v
python -m unittest discover -s backend/scripts -p test_rrgh_map_supervisor.py -v
mkdir -p /tmp/rrgh-completion-20261102
git show ec635afb75db606879ac95c7d2730ad899d54bb3:backend/config/gorge-campaign-wave-058-20261031/PLAN.json > /tmp/rrgh-completion-20261102/PLAN.json
git show ec635afb75db606879ac95c7d2730ad899d54bb3:backend/config/gorge-campaign-wave-058-20261031/ALLOWANCE.json > /tmp/rrgh-completion-20261102/ALLOWANCE.json
git show ec635afb75db606879ac95c7d2730ad899d54bb3:backend/config/gorge-campaign-wave-058-20261031/REGION-PLAN.json.z.b64 > /tmp/rrgh-completion-20261102/REGION.b64
git show db5abf719445b2fcc52c385f2218653a60b76198:backend/config/official-source-intake-20261102/official-source-candidates.json > /tmp/rrgh-completion-20261102/catalog.json
python .github/automation/rrgh_required_inventory.py \
  --spec .github/automation/rrgh-geographic-requirement-v1.json \
  --plan /tmp/rrgh-completion-20261102/PLAN.json \
  --region /tmp/rrgh-completion-20261102/REGION.b64 \
  --recovery .github/automation/evidence/20261102/recovery057-report.json \
  --database /tmp/rrgh-completion-20261102/inventory.sqlite \
  --summary /tmp/rrgh-completion-20261102/inventory-summary.json \
  --overview /tmp/rrgh-completion-20261102/overview.jsonl \
  --plan-sha256 982bf03c6053808daeb55929cd33d6ed1f1bf00c11d0de1ba247fbb742b73833 \
  --source-sha ec635afb75db606879ac95c7d2730ad899d54bb3
python .github/automation/rrgh_source_window_intake.py \
  --spec .github/automation/rrgh-geographic-requirement-v1.json \
  --catalog /tmp/rrgh-completion-20261102/catalog.json \
  --windows /tmp/rrgh-completion-20261102/source-windows.jsonl \
  --summary /tmp/rrgh-completion-20261102/source-summary.json
python .github/automation/rrgh_controller_preflight.py \
  --plan /tmp/rrgh-completion-20261102/PLAN.json \
  --allowance /tmp/rrgh-completion-20261102/ALLOWANCE.json \
  --audit .github/automation/evidence/20261102/audit057.json \
  --cutover .github/automation/evidence/20261102/cutover-not-activated.json
# Expected final exit code: 2 (activation intentionally blocked).
```

The generator can rebuild from a later exact independently recovered checkpoint;
the accepted position numerator must reconcile before its output is used. The
reporting tools are not yet wired into live recovery. Package evidence adapters,
protected persistence of detailed inventories, final native package QA, and iPhone
airplane-mode acceptance remain outstanding. No product-completion claim is made.
