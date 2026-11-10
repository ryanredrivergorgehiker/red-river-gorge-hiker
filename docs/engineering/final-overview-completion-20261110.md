# Final overview completion candidate

Status: engineering candidate, not activated. PR114's native repair queue is running separately. The first live repair wave1420 independently accepted100 tiles, for273,968 verified raster positions. This candidate must not replace the running native controller before its verified completion boundary.

The remaining691 lower-zoom positions all have zero consumed attempts. They are hiking189, terrain182, leaf-on128 and leaf-off192 across zooms10–15. Lower-zoom USGS coverage is already complete. After all373 native repairs pass, a four-parent pilot exercises an original accepted seed, a map edge, and repaired native provenance. Subsequent batches use at most128 fresh parents, only when every required child is already independently accepted and all metadata/range reads fit the original allowance.

The coverage helper proves the exact alpha mask resulting from the original fixed native tile grid and the existing Lanczos overview renderer. Transparent pixels outside that grid are permitted; missing pixels inside it, extra exterior coverage, omitted required children and changed child bytes are rejected. The historical renderer and native source quality remain unchanged. The output verifier uses this rule only under the exact final-overview authority.

The44 accepted seed jobs retain their original proof types:32 original seed jobs/320 tiles and12 second-stage jobs/116 tiles. The reader checks their exact pinned receipt generations and hashes, original output member ranges, and pixels. It never invents an ordinary campaign receipt. All prior ordinary/typed recovery receipts and native repair histories remain intact.

Local synthetic integration completed all691 parents in nine batches, ending at278,278 raster positions and zero remaining. Every allocation was charged in full for a modeled cumulative USD118.9162152323808848857879640, below the original USD123 admission limit. Synthetic results are tests and add no live accepted tiles. The actual-renderer tests pass for exact edge alpha, low zooms, explicit seed proofs, missing/extra children and rehashed interior holes. GitHub QA also reproduces the frozen native queue before testing this final phase.

Activation requires a successful current native queue settlement, exact state/receipt enrollment, passing QA and a live independently verified four-parent pilot. The final raster hold explicitly leaves `finalPackageDeliveryComplete:false`: consolidated phone-package sizing, complete delivery verification and physical iPhone acceptance remain required. The ChatGPT scheduled engineering task stays disabled.

The verified tile/package catalog now applies the same scoped coverage rule, so valid boundary outputs retain their independently checked package membership instead of losing optional catalog evidence. Its exact prior module hash is pinned for the first transition. Two encoded-tile/archive tests verify valid edge membership and reject a rehashed, repackaged interior hole. All56 catalog regressions pass; the historical catalog-hook fixture first strips the separately reviewed overview/pair hooks before checking the isolated catalog addition. The updated source publication smoke test still rejects all nine unsafe mutations.
# Bounded ownership history

The fully retained native and final-overview verification summaries exceed the
old64KiB GitHub Contents response limit. The final-phase source transition now
installs one exact reviewed ownership reader allowing a1MiB API envelope and
512KiB decoded state, with explicit base64, declared-size and decoded-length
checks. Repository, workflow, actor, branch, run, dispatch and plan checks are
unchanged. Oversized or malformed state still fails closed. The native queue
continues on its existing source until the final-phase transition.
