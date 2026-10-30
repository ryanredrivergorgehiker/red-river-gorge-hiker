# Controlled full-quality map campaign

Owner direction on October 30, 2026 replaces the USD8 campaign ceiling with
USD25 cumulative authority, including prior work. Repeated batch approval is
removed. The USD1/month storage target, USD350 Actions hard stop, restricted
identity and private staging prefix remain. No production deployment or accepted
package replacement is enabled.

The first finite wave assigns 512 new jobs /5,448 full-quality tiles across all
five raster layers, spatially grouped for reuse. Forty-four accepted jobs,
436 raster tiles,320 Sunlight assets and all original cache/claim masters are
excluded and preserved. The inherited raster engine and quality profiles are
unchanged. Only the coordinator and budget bookkeeping are new.

The resource envelope reserves USD0.6456 including20% contingency. The complete
historical USD0.70 releases remain charged conservatively. A USD2 completion and
recovery reserve prevents admitting waves past USD23; it is part of the USD25
ceiling, not extra authority. Historical storage is conservatively reserved at
1GiB. Every admission checks aggregate continuing storage against USD1/month.
Planning estimates and measured HTTP bytes/operations are not provider invoices.

Every wave has a create-only campaign-sequence fence and finite producer and
independent-recovery slots. Every child receives a durable reservation before
network/native work. Confirmed unused child capacity is evidenced in its new
immutable completion record; failures retain the full child allowance. A new
wave can use a closed predecessor only after matching its generation-pinned
independent recovery and exact carried ledger. Old allocations are never erased
or reopened. Ambiguous waves retain their entire allocation and stop progression.

Existing accepted shared-input proof covers all13 vector types, weather,static
and Sunlight; raster workers do not fetch the entire shared payload again.
Original cache selections and second-stage deltas are recovered once per wave.
New official public-source raw ranges are a bounded working cache, reused
throughout the geographic wave. Completed outputs, exact source identities and
complete source ledgers are durable. Future misses use the existing conditional
ETag/length-bound source path; a changed source fails. This prospective policy
does not delete or rewrite any existing cache. New durable raw-cache retention
is not assumed necessary for recovery of already-completed output jobs.

Independent recovery verifies every output hash, tile coordinate, dimensions,
alpha coverage and nonblank pixels and measures adjacent edges. That same read
builds genuine partial native-format package parts, with generation-pinned GCS
chunk readback. Partial parts are private candidates, not complete regional
packages or published catalog entries. Native256MB/60,000-member limits apply;
the obsolete aggregate8GiB planning assumption does not lower image quality.

The renderer never retries completed work. The worker stops before source,
storage, time, disk or output limits. Each terminal receipt records actual use,
reservations and a new settlement. A crash before terminal closure retains the
whole wave allocation; deterministic job receipts remain recoverable and require
explicit reconciliation before further production. No silent rerender is allowed.

Validation: ten new focused tests, including a genuine existing-image replay
through checkpoint writes, fresh recovery, pixel verification and package
assembly; a separate native handoff uses existing local cache/service metadata
with networking disabled. These are not repeated raster benchmarks or iOS CI.
