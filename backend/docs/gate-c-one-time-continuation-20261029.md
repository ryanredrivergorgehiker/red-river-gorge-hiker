# Owner-authorized one-time cumulative continuation

Owner approval is specific to the existing twelve-job stage and the same $0.35
release. $7.65 remains locked. The old plan and receipts remain immutable.

The new source-pinned plan binds the original plan and exact generation/SHA
references for its closed bootstrap and reconciliation receipts. It carries all
35 write / 13 read HTTP requests, stored bytes, original run windows, and a
conservative additional 1 MiB read / 16 KiB storage uncertainty allowance. It
preserves original per-job source reservations, all previous completed jobs and
the exact original twelve unfinished jobs. All new slots plus carried usage must
fit the original cumulative physical limits and funded worst-case cost.

Before private input recovery, the new bootstrap claims its own slot and creates
a fence at the OLD previously unused worker claim key using ifGenerationMatch=0.
An existing worker claim or competing continuation causes a 412 stop, with no
retry. The fence permanently binds that old slot to the new plan/claim. The two
old receipts and their claims are then independently generation/hash verified;
unexpected history, ambiguous HTTP, or any original raster attempt fails closed.
A separate immutable transition record retains the old allocations and used
reservations. Neither an old receipt nor an existing protected object is changed.

The exact private seed ZIP is received through the established expiring Actions
secret. Its six accepted GCS payloads are reused, with exact catalog/member
lineage checked; no seed pack is uploaded again. The accepted Base is read in
full at its numeric generation and checked against the corrected deployed
SHA256 92542003f2d6d11b9b1c9fa04ec44284c5ea492df5d30bb95079a06969014da9.
Vector, weather, static JSON/image hashes/decoding and complete accepted Sunlight
are validated before any raster attempt or production-worker claim.

New slot total: 400 MiB storage, 588 MiB GCS read/response reservation, 150 A,
476 B, 12 attempts, 10200 active slot seconds, 2 GiB official source transfer,
2000 requests, one worker. Entire workflow timeout is 157 + 16 minutes; adding
both prior whole-run windows is below the original three-hour ceiling.
Cache growth remains capped at 224 MiB; each full-quality output at 8 MiB and
closed cache ledger snapshots collectively at 32 MiB. Guarded failure preserves
attempt/source reservations and new cache deltas. No quality reduction or retry.

A fresh runner verifies every newly checkpointed cache member/output hash and
expected tile inventory, decode, alpha, nonflat pixels, and new/new or new/prior
edges. It selectively reads only the old neighboring tiles needed for that QA;
completed Sunlight and source packs are not needlessly downloaded again.

Nine new transition tests cover approval binding, cumulative carry-forward,
history/generation/job changes, missing receipts, runtime limits, and old-worker
claim collision. A separate offline integration check verifies the actual saved
seed and all six reused catalog bindings without contacting GCS or running a
raster job. Prior passing suites and benchmarks are not repeated.

The temporary transfer secret must be retired after successful intake, retaining
only nonsecret expiry/byte/hash evidence. No IAM, bucket lifecycle, production
package, deployment, protected merge, new spending release, or owner iPhone test.
