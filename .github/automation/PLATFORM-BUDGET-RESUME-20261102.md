# Owner-authorized GitHub budget policy and Wave070 resume

On November 2, 2026 the owner explicitly superseded the controller's local GitHub
budget gate, confirmed the November reset and account stop protection, and
directed production to resume. The supplied account screenshot displays Actions
spend of $0.00 against $382.00. This is owner-supplied evidence, not a connector
billing read. GitHub account settings are unchanged.

The local $346.73 estimate and its October 30 basis are retained as historical
metadata only. Future dispatches rely on GitHub's platform enforcement and do not
increment or enforce that obsolete estimate. Source quality, Cloud allocations,
exclusive ownership, authentication, immutable receipts and no-replay controls
remain enforced.

Wave069 run 41501582627 successfully produced and independently recovered 50
tiles. The successor was published before the obsolete budget gate stopped its
dispatch. The additional failure-handler error came from refusing to modify the
already-advanced allocation. The handler now recognizes that exact recovered
parent and preserves the successor without another error or any replay.

The exact prepared Wave070 source is
`9e0f8e47e6aeff1e33e4a1415a6045af87212bed`, plan
`72bab505f9a7212d324234f7a12f8c7c8a7751322fe0782f1a0c6402d3f32a28`.
Its predecessor receipt is
`feae06e5cfbbdf1d7d892526aa6ed8f6ea10704385d3bbad0a7dc9991e4ba540`,
generation `1793644547352505`. Accepted inventory is 118,782 raster tiles and
11,268 jobs before resumption.

An owner-authenticated launch may probe an unclaimed prepared successor only
when its sequence and checkpoint exactly match the recorded recovered parent.
The existing authenticated readback verifies the receipt and unused Cloud claim
before production activation. Running, publishing, halted or ambiguously
dispatched allocations cannot use this resume path. No consumed production run
is rerun.

Regression coverage includes stale estimates, explicit policy authorization,
exact predecessor checks, stale writers, conflicting producers, ambiguous POSTs,
source identities, and preserving a successor when its parent reports failure.
