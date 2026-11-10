# Remaining overview edge coverage

Engineering candidate only; not enrolled in production. Native production remains at the independently verified wave1419 boundary while the final native repair queue is validated.

The pinned original orchestrate_gorge_region.py overview renderer already omits children outside the fixed regional XYZ grid, builds a transparent RGBA mosaic, and resizes it with Lanczos. The later strict verified-child reader and generic output verifier currently reject every non-opaque parent. That excludes valid regional edge overviews along with truly missing imagery.

The proposed coverage verifier derives the exact expected alpha channel recursively from the unchanged zoom16 native grid for the existing bounds[-83.8,37.65,-83.4,37.95]. Every required child must exist and have its own verified coverage. Only coordinates outside that grid are omitted. It rejects both holes inside the required coverage and invented opaque pixels outside it; native tiles and interior overviews still require full opacity. The renderer, source resolution and required tile positions are unchanged.

Five local tests passed: fully opaque native/interior tiles, exact agreement with the original RGBA Lanczos operation for edge positions at every zoom10–15, a known northern edge with exactly two required children, rejection of missing interior and invented exterior pixels, and exact required-child selection. These tests use synthetic images and accept zero production tiles.

Remaining integration: resolve the44 accepted seed jobs from their existing bootstrap/second-stage proofs; include verified native repair histories as ordinary child provenance; enroll exact edge-aware dependency and independent-recomputation checks prospectively; bind scoped generic output validation; run real pilots and then the remaining691 lower-zoom tiles. Final consolidated package assembly and physical iPhone testing remain separate acceptance steps. No scheduled ChatGPT task is enabled.

The candidate seed reader now preserves the two actual proof types:32 original accepted seed jobs/320 tiles through the immutable input proof, plus12 independently recovered second-stage jobs/116 tiles through their original job checkpoints. The union is exactly44 jobs/436 tiles. Two additional tests pass, including six missing, changed, duplicate or falsely successful proof cases. Protected seed readback has not yet run under a new funded overview allocation; this remains a candidate reader, not new acceptance.
