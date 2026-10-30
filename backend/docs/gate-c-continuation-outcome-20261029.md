# One-time continuation: stopped before raster production

Run 40980260310 used source `8fac639fd887f1b1a43847bfe5bcca6cfdd05fa0`
and immutable plan `1b2612084503c2760ab31c2ccd78dac6c8fda63086f76471666483f8792b60a0`.
It verified the 309,600,543-byte private seed, reused all six generation-pinned
seed packs without uploading their payloads again, and saved the audited
one-time transition. The old worker was fenced with a create-only claim.

The complete 140,984,320-byte accepted Base independently passed SHA-256
`92542003f2d6d11b9b1c9fa04ec44284c5ea492df5d30bb95079a06969014da9`
and GCS MD5 at generation `1791470288796565`.

Input extraction then failed with KeyError before manifest or vector/weather
validation. The deployed builder uses GNU tar with `.` as its source, producing
`./NATIVE-MAP.json`; the importer indexed the literal member names and looked
up `NATIVE-MAP.json`. The deployed CI explicitly checks that dotted member name.
The narrowly scoped offline fix accepts a single leading `./`, rejects path
traversal, duplicate aliases, links and special members, and emits finite
diagnostics for missing required members. Seven new offline regression tests
pass, including an archive generated with the deployed GNU-tar flags.
These tests are synthetic parser fixtures, not validation of actual private
vector/weather payloads. No existing benchmark or native CI was repeated.

No raster attempt or official-source request occurred. Independent recovery
was correctly skipped because no worker receipt existed. The bootstrap claim
is closed; its complete allocation and failure receipt remain retained.
Neither its unused balance nor the older closed claims may be reopened.
The worker's 8 MiB read allowance cannot accommodate another 134.453125 MiB
Base read; the 400 MiB recovery slot is reserved for recovery, not replacement
bootstrap. Do not dispatch this offline patch under the old source fingerprint
or silently repurpose either slot. This owner authorization was one-time only.

Current-run GCS measurements including final receipt: four Class A and thirteen
Class B requests, 141,230,404 media-read bytes, 141,237,374 response bytes,
3,294 newly stored bytes across four immutable audit objects. All 17 responses
were HTTP 200. Existing seed payloads and protected packages remain unchanged.
Costs are estimated using the previously approved conservative rate model;
current provider billing has not been read. The $0.35 stage release remains the
ceiling and $7.65 remains locked.

The temporary GitHub transfer secret was removed after the successful seed
intake; its short-lived provider references expired. Nonsecret audit evidence
is retained separately. No IAM, lifecycle, Firebase, package/catalog activation,
protected branch, or budget setting was changed.

Next: validate the repaired reader against an exact privately preserved Base
snapshot before proposing any live repair. A new immutable repair allocation
would need to preserve this closed claim and all earlier history and fit the
same cumulative ceilings; no additional funds or closed-allocation reuse is
authorized by this source-only fix. Full-Gorge production remains blocked.
