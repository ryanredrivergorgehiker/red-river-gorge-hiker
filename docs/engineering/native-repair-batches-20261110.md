# Finite native repair queue

The accepted wave1419 pilot added 31 tiles across three jobs after independent output and package readback. Production is deliberately paused at 273,868 / 278,278 raster tiles. This candidate completes the remaining native queue from that exact settlement; it does not claim that the subsequent 691 lower-zoom tiles or final phone packages are finished.

## Scope and evidence

The finite queue contains 373 native jobs covering 3,719 positions across hiking, terrain, leaf-on, leaf-off and USGS. Every candidate must have a recorded complete original-source pixel mask within its original read/time bounds, with zero Cloud writes and no production-attempt consumption. The fixture is content-addressed and cannot change during the queue. Source checks use actual official rasters, including the full terrain halo. The context fixture adds 14 DEM and 14 leaf-off COGs needed for existing edge footprints; output bounds stay `[-83.8, 37.65, -83.4, 37.95]`.

Read-only proof runs: 42833189965 and 42840845305 for changed-source cases; 42835102907, 42839530469 and 42847408310 for adjacent context and consumed COG cases; 42841026585 for NAIP and USGS. Local initial proofs are identified separately in the manifest. A successful workflow alone does not authorize a candidate: its individual complete mask, dimensions, source-selection hash and metered use must all match.

## Production behavior

Each wave selects at most 12 jobs and four per family. Every job has exactly one historical consumed attempt and may consume its final second attempt once. Accepted output bytes, quarantine history, global attempt counts, map extent and rendering quality are preserved. Each settlement records its exact recipe, recovery receipt, attempted jobs and independently accepted partition. Reconstructing this history must reproduce the original pinned ledgers and every intervening selection.

Temporary HTTP 500/502/503/504 responses may retry once for GET/HEAD, within the original request, byte and time reservations. Each request is charged before I/O; no allowance is refunded. Authentication errors, changed identities, partial bodies and exhausted bounds still fail. This does not replay a production job or reset a consumed attempt.

The unchanged aggregate allocation is independently admitted against the USD125 campaign ceiling, USD2 monthly storage ceiling and USD2 protected reserve. Native queue exhaustion creates an explicit verified hold. If all 373 jobs succeed, the accepted total is 277,587, with zero native positions and 691 lower-zoom positions remaining. A failed final attempt remains unaccepted and consumed; it is never silently scheduled a third time.

## Validation and activation

The integration test starts from actual wave1419 records, runs the full finite selector through synthetic successor plans and trusted publication validation, charges the full allocation on every synthetic wave and checks the final hold. It also rejects eleven mutations to attempt history, acceptance, recovery identity, source selection, context, geography and budget. Test fixtures add zero live accepted tiles. Existing pilot, handoff, publication, completion and source-pixel/attempt guards must pass before activation.

Actual pilot authority: plan `943a8fc21d34ce6dda1492c1ad80c58e56d6aa61da6660ecc50d70296c90326d`; recovery generation `1794320163909534`, SHA-256 `54ee342bcf4205229ec1450cea5f0b2914a9b0763193c9e8bb227afb54b6e8bf`; source commit `230f3c6097af85cb7e093b9a81a68c5cc3b9ff51`; production run 42831781398.

Activation requires the frozen manifest, passing complete queue QA, reviewed controller merge and a fresh successor from that actual settlement. Historical claims are never rerun. The ChatGPT engineering task remains disabled. Lower-zoom edge/seed integration and final package delivery validation continue separately.
