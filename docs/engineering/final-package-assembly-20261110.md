# Final offline package assembly

Candidate engineering only. No new Cloud package allocation or delivery catalog
has been activated by this change. The native repair queue and its accepted
outputs remain unchanged; the final-overview change is PR115.

The final inventory must include all34750 accepted jobs covering278278 raster
positions, plus the original340 shared files (73865407bytes):13 vector families,
the accepted320 Sunlight assets and weather/static dependencies. The earlier
overview dependency index omitted1770 already-completed USGS lower-zoom jobs
because those were not inputs to the four derived imagery/terrain layers.
Final packages restore their exact original acceptance lineage by walking the
1357-to1322 predecessor chain. Wave011 salvage, wave289 completion, partial
recoveries and the44 original accepted seed jobs retain their explicit types.

Metadata reads are divided into finite96-wave slices. A missing or duplicate
slice fails the complete inventory check. Assembly reads only generation-pinned
accepted extents, verifies every tile hash/pixel and copies the unchanged bytes
into the existing deterministic iPhone TAR format. It does not rerender a tile.
The existing256000000-byte,60000-entry and64-part-per-group limits remain.

The next integration steps are the separately funded metadata/assembly runner,
fresh independent remote readback, complete shared-reference validation,
authenticated index and inactive catalog candidates, and delivery validation
through the existing Base entitlement path. Full raster completion alone does
not activate these catalogs or establish physical iPhone acceptance.
