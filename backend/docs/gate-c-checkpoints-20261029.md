# Gate C: bounded checkpoint engineering

This change is source-only. Existing production, source caches, immutable R4
plans/receipts, deployment identity, IAM conditions, accepted Base, and native
CI are unchanged. It contains no workflow change, dispatch, lifecycle mutation,
delete, overwrite, deployment, budget increase, or full-region enable switch.

## Reservation and recovery model

`gorge_checkpoint.py` partitions a pinned plan into a finite set of spending
slots. The sum of every slot's maximum storage, external reads, Class A/B calls,
official-source bytes/requests, child seconds and attempts must fit the plan.
Each slot creates a deterministic claim with `ifGenerationMatch=0` before doing
work. A crash, lost response or competing claim cannot reclaim or refund it.
The entire allocation remains charged even if the runner disappears. A fresh
runner must consume another slot. No mutable head pointer or overwrite privilege
is required. The plan hash names the checkpoint namespace; the explicit allowance
must bind that exact plan hash. A new plan is a new funding decision, not a reset.

The local meter reserves before each operation, including metadata responses,
failed/short reads and every child maximum. Retries are never implicit. Claim
collisions stop. The existing workflow must stay single-concurrency and its
ordinary rerun mechanism cannot reuse a slot. Repeated external launches can
still produce billed rejected requests: this application guard is not a GCP
account billing cap. Count orchestration/claim attempts in the final measured
plan and do not offer an uncapped retry loop.

Create receipts include numeric GCS generations and content hashes. Full reads
pin both generation and precondition and verify SHA256; uploads verify GCS MD5.
Partial recovery pins the same generation, checks exact Content-Range and verifies
the selected member's SHA256. GCS error bodies and credentials are not logged.
Only the existing bucket/checkpoint prefix is supported; no listing, redirects,
implicit retries, service-account keys or delete/overwrite methods are exposed.
Per-job receipts are committed immediately after their output packs. They remain
recoverable even when the final slot receipt was never written. Missing or
ambiguous prior receipts stop rather than silently rerendering a completed job.

## Packed deltas and selective recovery

`pack_delta` streams packs of at most 64 MiB from explicit hash-verified entries.
Raw concatenation plus private offset/size/hash indexes allows range recovery of
only needed members. Previously saved hashes may be skipped only when their
verified generation-bearing catalog references are retained separately.
Neither packing nor recovery assumes the whole regional source cache is retained.
New retained bytes are cumulative: there is no rotating allowance based on deleting
old objects. No lifecycle rule is assumed, and soft delete is not automatic expiry.

`gorge_cache_selection.py` exports explicit `(source identity, block number)`
selections under the existing cache lock. It checks SQLite integrity and records
the original ledger snapshot hash, limits and transfer totals. It never changes
old ledgers. Range-recovered members can seed a separate new local cache with
verified identity, block extent and content hash. New source transfers remain
subordinate to the already durable slot allocation; a new local ledger never
refunds an old slot. Selected service `.json`/`.bin` pairs can use the same pack
format; they still need an explicit dependency selection and ledger provenance.

`gorge_prior_receipts.py` verifies a pinned saved evidence ZIP and its original
R4 recipes, job definitions, output hashes and ledger fingerprints. The returned
completion inventory excludes those jobs from new assignments. It does not
change historical receipts or claim source-cache payloads are restored.

## Worker integration and deliberate limits

`gorge_guarded_worker.py` invokes the existing native engine in a single bounded
child. Its COG and service HTTP paths are metered before network access. The
parent reserves the entire child source/time allowance before launching; local
one-use tickets prevent replay. Engine hashes, receipt identity and actual output
hashes are checked. Existing source-cache limits are not raised. Child requests
cannot exceed the parent allocation even if a fresh local cache is used.

`run_gorge_checkpoint_slot.py` defaults to offline preflight. Execution additionally
requires a plan-bound explicit Cloud Storage allowance, ongoing storage funding,
the original exact producer workflow context, first run attempt, a fresh private
workspace, and at most 12 job assignments. It writes only private checkpoint data.
Trial-credit balance never substitutes for approval. Account observations are
point-in-time evidence, not current meter readings.

The bulk flag is explicitly required to be false. This is a bounded engineering
adapter, not an automatically scheduled full-Gorge pipeline. Before any regional
rollout, verify the adapter on live GCS, pin/select useful old cache and private
shared inputs, calculate all spatial/dependency assignments and reservations,
and connect bounded sequencing to the authorized workflow. Overview jobs need
verified child outputs in their private workspace; the driver intentionally does
not discover or restore whole dependency trees. No such rollout is performed by
this change.

## Validation and remaining release gates

Focused offline tests exercise competing writers, ambiguous committed writes,
crashes between per-job and final receipts, independent selective recovery,
original-ledger preservation, generation/range/hash checks, source/GCS limits,
plan/code pinning, completed-job exclusion and the two-attempt ceiling. Synthetic
fixtures and persistent-store emulation are not live GCS acceptance.

Use preserved real R4 outputs for a private local pack/recovery check without
source downloads or raster regeneration. A subsequent live drill should use
those already saved bytes, two finite slots, no new source reads or rendering,
explicit bytes/request/time ceilings and independent recovery. Preserve the live
numeric generations and actual response counts privately. Only then measure one
new bounded spatial shard and evaluate its extrapolation against the complete
approved cost envelope. Full regional pixel/seam/coverage QA, private shared-input
recovery, package sizes, backend delivery, activation/rollback and offline native
rendering remain separate acceptance gates. Passing native CI is not rerun here.

Official API semantics:
- https://cloud.google.com/storage/docs/json_api/v1/objects/insert
- https://cloud.google.com/storage/docs/json_api/v1/objects/get
- https://cloud.google.com/storage/pricing
