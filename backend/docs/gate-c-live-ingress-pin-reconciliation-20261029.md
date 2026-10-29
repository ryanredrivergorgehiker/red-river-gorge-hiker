# Gate C live ingress and accepted Base pin reconciliation

The private seed transfer succeeded in run 40957497769. All six payloads and
catalogs are immutable, generation-pinned GCS objects with complete SHA256
readback. The ZIP receiver verified 309600543 bytes and the expected 307b31fe...
SHA256. No source processing or raster attempt began.

The Base preflight used the obsolete full-preflight checksum 3204fd6294be8bbee177ee33d35ef39e45d42843f228e196fc3e30404db175fe.
Both original successful deployment logs, runs 37793475399 and 37823038637,
record the accepted 140984320-byte Base SHA256
92542003f2d6d11b9b1c9fa04ec44284c5ea492df5d30bb95079a06969014da9.
The authoritative Lane20 register already superseded the stale handoff hash on
October 8. This is a source pin correction, not evidence of package mutation.
Current live metadata identifies generation 1791470288796565, the expected size,
and MD5 Kf9K26MSnTxeZ6YVPvHipQ==. A full live hash against the corrected pin and
the private input validation remain pending. The failed run logged only
ValueError, so the exact failed predicate was not retained; stale SHA is a
confirmed code defect and explains rejection of the deployed accepted bytes.

This correction adds finite safe integrity error codes and hash/size/generation
diagnostics to a durable failure receipt. No payload, token, URL, or exception
string is logged. Two focused offline failure tests pass. Historical test suites,
native CI, and benchmarks were not repeated.

The consumed plan 42a3aed271084ebc087eb0028ac4ec32b6f07b3fce3cf5262da90a7fd25de42b
and its source pins are deliberately unchanged. Modified source cannot execute
that configuration. Slots 0 and 2 are closed and nonrefundable; slot 1 is unclaimed
and has only 8 MiB GCS read reservation, insufficient to reacquire the 140984320-byte
Base. Do not reset or reuse claims, silently swap the plan, or unlock campaign
funds. Reconciliation run 40958769659 successfully recovered the failed receipt
and inspected small Base ranges; it did not find the manifest in those windows.

Observed cumulative usage: 16 new private objects, 308693877 stored bytes;
451597391 media read bytes; 35 write HTTP requests and 13 read HTTP requests.
HTTP write counts conservatively upper-bound Class A charges, including resumable
upload chunks. Response bytes are bounded by 451641069 including one unobserved
receipt response. Conservative established planning rates give $0.105732 for
first-month storage, operations and egress, or $0.126878 including 20% contingency.
These are estimates, not current Cloud billing readings. Incremental ongoing
storage with contingency is about $0.010350/month. $7.65 remains locked.

A proposed reconciled continuation fits the existing physical ceilings and
$0.35 release using private Drive seed delivery again (zero repeated GCS seed
reads/writes), a 224 MiB new-cache cap, unchanged output quality, and full recovery
of new data. Its new reservation totals would be 400 MiB storage, 588 MiB reads,
150 A, 476 B, 12 attempts, 10200 seconds, 2 GiB source transfer, 2000 source
requests, one worker. Adding all recorded prior operations remains within the
original ceilings (10342 seconds including both complete previous run windows).
All old receipts/claims remain preserved. Because the established policy makes
closed allocations nonrefundable, engineering has not executed this proposal or
silently reclaimed its unused allocation. The specific decision is permission to
replace confirmed unused closed allocations with a cumulative reconciled
continuation under the SAME $0.35 release, with no additional funds. The durable
transition and continuation coordinator still require implementation and offline
validation before execution. This document does not grant that exception.

No IAM, bucket setting, Firebase deployment, protected package, protected branch,
production catalog or native acceptance gate changed. The temporary seed secret
contains expiring provider references; they expired after ingress. The repository
entry remains present. Full-Gorge processing and physical iPhone testing remain
blocked by the unfinished twelve-job/input/recovery gates.
