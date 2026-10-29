# Gate C native Storage API ingress — prepared, not live

The verified private Library seed can be materialized in the engineering
runtime. Its expected byte count and SHA-256 match. This runtime has no Google
ADC, GitHub OIDC request environment or Cloud SDK credential. A bare Storage
endpoint HEAD returned HTTP 400; this is reachability evidence only, not an
authenticated object operation. Cloud Console is unavailable in this browser.

The existing producer identity remains direct WIF, restricted to the exact
producer branch, push event, repository/owner IDs and workflow. The GitHub
runner can authenticate to GCS; the exposed GitHub connection has no secret
write or private binary input facility. Plugin discovery found no native GCS
transfer connector. None of this establishes an IAM regression.

## Implemented transport

`gorge_resumable_ingress.put_file` uses the native JSON API with an existing
funded `Slot` and WIF-backed `GCS` transport. It checks the entire local input
hash before I/O; reserves storage, requests and full verification reads before
initiation; requires create-only `ifGenerationMatch=0`; sends binary chunks;
handles HTTP 308 and at most two prepaid interruption/status recoveries; and
checks bucket, object, byte count, server MD5 and generation. Acceptance requires
a complete exact-generation readback with matching SHA-256. No custom SHA
metadata is treated as proof of object content.

Session URLs are credentials. They are confined to a mode-0600 private journal,
never returned in evidence, and removed from the journal after acceptance.
No redirects, automatic new sessions, overwrite, deletion, listing, deployment
or credential discovery are implemented. Interrupted processes consume their
original slot allocation; a journal cannot be reused to reset the budget.
Cross-process recovery requires coordinator reconciliation and a separately
funded slot; that coordinator wiring is not claimed complete here.

Fourteen focused offline protocol/budget/integrity tests passed. These are
synthetic transport tests, not a live GCS drill or map benchmark. No passing
native CI, prior recovery drill or source processing was repeated.

## Budget integration still required

With 16 MiB chunks and two prepaid recoveries per object, the whole ZIP needs
24 conservative Class-A request reservations plus one full readback. Prefer
the six existing raw packs for selective recovery and avoid storing both ZIP
and packs. The six pack uploads reserve 49 write/status requests and six full
readbacks; six catalog writes plus claim/final receipt bring the write envelope
to 57. This conservatively counts physical requests, even though Google's
resumable upload billing unit is a completed object. The old bootstrap slot
has only 20 A requests and no B reads, so it MUST fail until rebound within
the existing stage totals. This is not an increase in spending authority.

The $0.35 released allowance, $7.65 locked balance, $1/month storage cap, all
stage hard limits and $350 Actions hard stop are unchanged. No GCS object
generation was created, no private seed was accepted remotely and no job ran.

## Smallest missing connection

Provide one secure machine-to-machine bridge between the verified Library
bytes and the existing WIF runner. One practical option is a write-only
GitHub Actions secret capability carrying a short-lived private seed download
descriptor to that exact workflow; it must never appear in source, workflow
inputs visible in run metadata, artifacts or logs. A connector exposing an
authenticated native GCS file upload in the Library runtime is another route.
Neither is available through the currently exposed tools. A resumable session
URI alone also needs a private delivery channel and authenticated readback;
publishing it is not a legitimate workaround.

No owner file download/upload is requested. No service-account key, Google IAM
change, new bucket or delivery architecture is required. Once that private
connection exists, rebind the bounded plan, verify accepted Base generation
and vector/weather inputs, complete cache-growth/coordinator safeguards and
execute only the authorized twelve jobs. Do not treat this transport component
as an integrated, dispatch-ready production candidate.

Official protocol references:
- https://docs.cloud.google.com/storage/docs/performing-resumable-uploads
- https://docs.cloud.google.com/storage/docs/resumable-uploads
- https://docs.cloud.google.com/iam/docs/workload-identity-federation

## Connection audit and implemented private input, later October 29

The existing GitHub connection was freshly verified against the authenticated
account and repository: it reports admin, maintain and push access. No connector
reauthentication is needed. Its exposed API explicitly excludes Actions-secret
operations, and there is no authenticated GitHub CLI in the seed runtime. Account
permissions and available connector operations are separate capabilities.

The earlier assumption that Library could directly issue a runner-readable seed
URL was incomplete: current materialization returns a workspace path and no URL.
Browser sign-in alone was therefore not a complete transfer solution.

The existing private Drive connector DOES return provider-signed, expiring,
read-only single-file download references. A 7,126-byte saved report was fetched
through such a reference with HTTP200 and its exact SHA256, without additional
authentication. No bearer URL or signature was logged or published.

Whole-seed upload was rejected before action invocation by a 100MiB connector
limit. The original ZIP was then split into four transport parts (80MiB each
for the first three; 57,942,303 bytes for the fourth). All four were saved using
the existing Drive connection and private engineering folder. Remote size and
owner-only permission metadata match. The original complete ZIP remains intact;
its SHA256 was preserved during splitting. No map processing was repeated.

`fetch_gorge_private_seed.py` now consumes a single Actions secret named
`RRGH_STAGE_SEED_TRANSFER`: a JSON descriptor of four freshly issued private
references. It requires the exact existing producer workflow context, validates
the host, read-only scope and expiry, bounds each response, pins every part hash
and the original whole-seed hash, and atomically publishes only a complete
verified file in private runner temporary storage. No redirects or retries;
errors suppress credential-bearing URLs. Six focused offline tests passed.

The descriptor must be issued immediately before the run, passed only through
the Actions-secret UI/API and removed after use. Do not save it in reports,
source, workflow arguments, artifacts or logs. The existing WIF mapping uses
repository ID plus ref; no identity or Google IAM change is required.

The exact missing account operation is creation of that private Actions secret
in this repository (REST equivalent: create/update repository Actions secret).
The existing Cloud Browser remains signed out; its last visible result is
incorrect credentials. An owner-completed sign-in in that browser enables the
secret-settings operation, while the existing connector continues all source
and CI work. No new authentication was requested during this audit.

GCS seed acceptance, accepted Base vector/weather validation and the twelve-job
run remain pending. GCS object operations and stage spending remain zero;
$0.35 unused and $7.65 locked. Remote part hashes will be checked by the receiver;
Drive metadata alone is not claimed as remote SHA validation. No production
workflow was changed or dispatched by this source-only addition.
