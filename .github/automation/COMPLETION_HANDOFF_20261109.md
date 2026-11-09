# RRGH completion engineering handoff — November 9, 2026, 09:41 EST

## Authority and current ownership

Ryan authorized: “Proceed. Remember to pause or update the scheduled task as needed. do what you need to to get it to 100%.” This authorizes the implementation, testing and deployment of the remaining original-scope completion work. The earlier plan-only restriction is superseded. Continue without asking again for the same scope. Preserve original quality, all accepted work, immutable receipts, consumed attempts, source identities, exclusive CAS ownership and the existing USD125 Cloud ceiling, USD2/month storage target and protected USD2 completion reserve. No budget, IAM, account, website, unrelated iOS or geographic output expansion is authorized.

The GitHub controller owns production. The ChatGPT engineering automation was paused during interactive changes and is being updated and resumed at handoff. Fresh-read live state before action; do not assume the snapshot below remains current. Do not compete with a new interactive repair.

## Verified live outcome

Repository: ryanredrivergorgehiker/red-river-gorge-hiker.
Controller branch: lane20/offline-production-preflight-20261029.
Source branch: lane20/map-producer-iam-design-20261029.
State: .github/automation/rrgh-controller-state.json.

Wave1330 run42634719476 independently verified 64 jobs /64 original USGS tiles, 91 adjacent edges and one package. Inclusive acceptance is 25,696 jobs /265,850 raster positions of278,278 required;12,428 remain. The controller settled1330 and automatically launched1331run42636531484, observed running. Do not count1331 until independent verification.

1330source29cc944f32c775b23c3dccfa479bfdfc3dac862f.
1330plan86d4a3933e20196f15f1e86582822c0e355aea0aa5717b8792501aa2ef39d4b4.
Independent recovery job129221536226; receipt:
- key: engineering/map-production/plans/86d4a3933e20196f15f1e86582822c0e355aea0aa5717b8792501aa2ef39d4b4/slots/00002/receipt.json
- generation:1794234983564324;bytes1512;SHA256ca5745f8f8b192d81276e4d75f3819d1629189d7eb69d81c4e6f961915668890.

nextCarry ALREADY INCLUDES the verified64: priorCompletedJobs25696,priorRasterTiles265850,chargedUSD85.94375780000872015953063974,storedBytes41274717920,priorSunlightAssets320. Monthly modeled storage1.383842756152153015136718750USD. Never double-add. Modeled Cloud is not OpenAI expense or an invoice.

Remaining as of1330:1,622 original-service USGS lower-zoom tiles;7,056 derived lower-zoom positions;3,750 native positions in376 consumed unaccepted jobs. USGS completion alone would reach267,472 and leave10,806; this is not full-product completion.

## Deployed changes and validation

PR105 https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/105 enables the finite1,770-position USGS z10–15 queue after native exhaustion and a real completion-waiting boundary rather than a false empty successor. It preserves original zoom-specific USGS labels. Exact-headb4d94c70195e3b724921baab046336923422863d passed offlineQA42629140670 and CI42629149994. Recovery handoff42629796426 settled1322 once and launched1323. The six-zoom12-tile pilot is1323run42629970002, plan c739759141fb56b19f5089afd974e77499c46c5e8c9ea85fe8d3e7b360e34e0d. It verified12tiles with12official requests and19.174producer seconds.

PR106 https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/106 enables64serial USGS jobs after the accepted pilot,120seconds/job, same1MiB/one-request child cap, same9,000-second producer slot and unchanged aggregate ceilings. It fixes the previous native-only recovery assumption: USGS saved checkpoints reconstruct service usage from verified responses, preserve prior ledgers and retain full uncertain-request reservations without source replay. Exact headcee2f1040028a50bbe16e4856cc80ef9c51be87e passed offlineQA42632979546 and fullCI42632987951. Merge d504341037e73b68a9472191c7385aef965dd5e7. State upgrade staged3676daba6e788f9a372ab58e26a184943b6cbbdb, activated atomically on1329claim42634051460.
Active digest:db01b6291fb4bcbfdc0ab787ad493768fad380d73e30720b9c078721cfddd2fe.
Production1330 proves the first actual64tile batch passed independent verification;1331 automatic successor observed. Its591-second cycle included a slow setup-gcloud installation, so do not extrapolate a full-completion ETA from one batch.

Rollback code anchor: lane20/rollback-before-usgs-throughput-20261109 at82cb758494a13e5f3a61b7cf0c575e8d93f900a6. Never restore its old state/ledger. A future fallback must preserve current inclusive carry and consumed work, retain the service-ledger fix, validate the in-flight V2 plan and change only prospective fresh batches. A blanket restore of V1 code would reject V2 plans. Current batches have succeeded; no rollback performed.

## Cross-wave overview implementation and actual provenance

DraftPR107 https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/107, branch lane20/verified-crosswave-reader-20261109, head6db222faf4bbe1bb288e4623b53e44cf525f9320.
This replaces the unintegrated November5 reader approach that could not decode production compact-v2 receipts and lacked trusted receipt acquisition. Do not redeploy that old JSON-only reader.

The new rrgh_crosswave_dependencies.py uses the actual production compact codec and selective range reader, exact generations/hashes, independent recovery -> worker -> detail -> job -> pack lineage, original recipe checks and complete child pixels. Offline tests cover all4layer renderers, fresh independent recomputation, wrong generation/recipe/count, missing/duplicate children, corrupt/transparent bytes and rejected partial/salvage/seed provenance.

Exact-source QA42634238956/job129218071614 PASSED at6db222... . Actual Git acceptance indexing PASSED independently on42631138774/job129207437799, branch lane20/completion-receipt-index-20261109,head1a8850064e3ef0315d527f82eab6a6b5dc30a540. Index:25,504 accepted jobs across1,322waves +44pre-campaign seed jobs explicitly requiring separate proof. Raw1,448,444bytes,SHA2561fea8db2f65861e50130856a152cec5862baee2a483ace4eef328a96930c4974. Exact baseline source2c121dfba317d918749acaadd6842be81c88fee1, plan e2631ee1ca7b5a8b0dd787afcabcf8abfbf9d76e3420f2dbdd28a2f33eaa4902,265702tiles.

The QA acquires four REAL cross-wave manifests:
hiking-15-8756-12645 fromwaves200/201/202;
terrain-15-8756-12645 from153/154/155;
leaf-on-15-8756-12646 from32/33;
leaf-off-15-8756-12645 from153/154/155.
Binding raw67,227bytes,SHA2560a99f404f20cda595e80f2da390e1dde877cd234ca33886dfe8615ca45aa1990.
Recover exact binding from RRGH_CROSSWAVE_BINDING_ZLIB_BASE64 in QA job129218071614; code verifier reproduces it from exact source and history. The immutable references are real; Cloud child-byte readback HAS NOT been performed yet. The transport tests are synthetic and count no production output.

NEXT: integrate this helper into the trusted planner/publisher and existing bootstrap/independent recovery hooks; bind actual manifests, fund all reads and do exact-source transition tests. Then enroll a fresh4parent pilot and require independent child readback and parent recomputation before further batches. USGS continues independently first. Do not merge the draft as if integration is already complete.

4,316 unaccepted z15parents have four accepted children in ordinary verified waves (hiking975,terrain1126,leaf-on1090,leaf-off1125). These are geometry/provenance candidates, not new accepted output. Full prior dependency analysis:6,388 interior parents recursively ready without native repairs;266 boundary/dependent parents;402 dependent on native gaps. All need appropriate byte verification. Add typed readers for partial/salvage and44seed jobs rather than faking ordinary receipts. Boundary work must preserve genuine pixels, original quality and the required map extent.

For efficient later32parent batches, calculate source read budgets explicitly: worst128children plus wave receipts/detail metadata; cap reference sizes; redistribute bootstrap/recovery classB reservations within the existing aggregate3000 only after tests. Do not raise aggregate budgets or immediately repeat hundreds of12parent waves. Cache verified metadata within each funded batch where safe.

## Blocked native work: new evidence

Read-only official source-mask diagnostic: branch lane20/source-mask-diagnostic-20261109,head3982af1a05095695e9defd3496e5d9d369b6814d,run42634892249/job129220329224.
Three fresh DIAGNOSTIC suballocations, each64MiB/128requests/600seconds; no Cloud credentials, Cloud reads/writes, map tiles, accepted-state mutation or old allocation replay.
- hiking-16-17534-25326:262144/262144 source pixels valid,655360sourcebytes,8requests.
- terrain-16-17537-25329:264196/264196 valid including required halo,4052697bytes,10requests.
- leaf-off-16-17537-25329:UNKNOWN; reached64MiB diagnostic cap after66850195receivedbytes/49requests. Log explicitly says Cumulative original-source byte ceiling reached. Do not call it a source hole. A separate bounded diagnostic can reuse/retain cache or use a sufficiently funded native-resolution inspection.
Total actual public-source transfer71,558,252bytes/67requests. No accepted tiles added. Exact current ETags/identities are in that log; compare historical protected pins before production enrollment.

Original-source history diagnostic: branch lane20/gap-history-diagnostic-20261109,headf6ce54061263984a28e70ab13505372766b0d340,run42636458210/job129225762632 PASSED. It uses the immutable receipt-chain plan pins to disambiguate duplicate historical folders; the first filename-only run failed at58 and was fixed. No production was affected.

All376 consumed native jobs /3750positions classified against their original allocation:
| Category | Source selection changed | Jobs | Tile positions |
|---|---:|---:|---:|
| Source-pixel-gap quarantine | Yes |235|2295|
| Source-pixel-gap quarantine | No |86|602|
| Other consumed/uncertain | Yes |18|106|
| Other consumed/uncertain | No |37|747|

Thus253jobs/2401positions have corrected or expanded source selection. This is eligibility evidence, not proof all pixels are now available. Both successful mask samples confirm the root cause for those exact positions:
- hiking originallywave38 had onlyN14E30; current selection addsN14E29, whose pixels fill the missing area.
- terrain originallywave63 had onlyN110E350; current selection addsN109E349 andN110E349, which cover the window.
- leaf-off originallywave60 also had onlyN110E350; current selection adds its two neighbors, but full-mask verification remains pending.

Of86 unchanged source-gap jobs,84/588positions lack full native window/halo coverage in current catalog metadata. Two other jobs, terrain-16-17585-25301 (3positions,wave681) andleaf-off-16-17585-25301 (11positions,wave688), have full BBOX coverage but still require actual mask/context diagnosis. Bounding boxes never prove pixels.

For55 other-consumed jobs/853positions, first recover and independently verify exact saved receipts/outputs where possible; do not blindly rerender. Inspect their actual historical failure evidence. The28leaf-on jobs/588positions are in the unchanged-source group, and may need exact salvage rather than source replacement.

NEXT after overview integration: create a prospective repair queue for changed-source positions with explicit original-allocation linkage, current source/ETag validation and full-mask preflight. Preserve attempt1 and all its charges; use only a newly reviewed finite allocation and the existing global two-attempt ceiling. Existing source/checkpoint engine allows at most2attempts, but current selector deliberately excludes any prior attempt, so repair needs a typed authorized policy and publisher tests. Never clear priorAttemptCounts, reuse consumed slots, hide source gaps, lower zoom/detail, fill invented pixels or overwrite accepted output. For edge/context cases, inspect neighboring official assets needed for the already-required XYZ windows and terrain halo; keep output extent and quality fixed.

## Completion and operational behavior

Success is all278278 unique required positions independently verified with no unresolved required holes, followed by complete package membership/readback, protected authenticated delivery and phone acceptance. Phone testing remains Ryan/other developer's separate acceptance gate; never claim it from CI. Do not alter the limited-coverage delivery contract or another developer's branch silently.

When healthy, production preflight is brief; it is not the engineering deliverable. Continue the next concrete implementation and validation artifact. Reuse these audits and exact passed CI. Do not end another scheduled run with only “reader missing integration” when integration is authorized and available. If a real permission, evidence or budget boundary blocks work, name it precisely. Do not claim unattended success just because the task is enabled.

Recovery: retain current receipt-only/published-successor, saved-checkpoint and pre-recovery setup-failure paths. An external setup-gcloud failure after a complete producer may qualify for recovery-only mode; never rerun production. The GitHub controller must keep exclusive CAS ownership and ambiguous dispatches retained. Any rollback affects future code/policy against CURRENT state; it never restores an old ledger.

Persist concise changes and exact evidence in the existing Lane20 register:
https://docs.google.com/document/d/1xiWk9KFPy_bQQ1nlJTDSWuBUGaTzySh5vXWPfjs0Ll0 .
