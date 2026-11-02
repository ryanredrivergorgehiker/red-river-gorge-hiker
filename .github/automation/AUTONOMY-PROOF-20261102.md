# Live autonomous production verified — November 2, 2026

The owner applied the exact reviewed provider-condition update in Cloud Shell and verified its before/after state. A fresh restricted-identity probe passed, recovered the protected predecessor receipt, and proved the Wave058 claims were unused. The controller then initiated two consecutive production executions with successful independent recovery and automatically initiated a third. No further Cloud administrator action is pending for this identity transition.

| Sequence | Automatically initiated run | Producer | Independent recovery | Accepted new jobs | Accepted new tiles |
| --- | --- | --- | --- | ---: | ---: |
| 58 | [41492671161](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41492671161) | success | success | 12 | 92 |
| 59 | [41493738368](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41493738368) | success | success | 9 | 45 |

Both complete workflows succeeded, including successor publication and dispatch. Wave059's source plan contains the exact generation/hash-pinned Wave058 recovery receipt. Its owner record identifies Wave058 as its automatic parent. Both live logs were separately run through the fail-closed auditor in the engineering workspace.

- Authenticated read-only probe: [41492358431](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41492358431).
- Wave058 recovery: SHA256 `f1134638363ca5f8100329915b7f8dd46d149ccbb5b5744f3bfbbf5c53c01c27`, generation `1793641313173416`.
- Wave059 recovery: SHA256 `76cdc0026a13d851082cb4d1817a899e6be743bf4c352df58437a95fded2f833`, generation `1793641623184497`.
- Automatic continuation observed: Wave060, [41494557108](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41494557108), parent Wave059.

At the Wave059 checkpoint, accepted totals are **11,165 jobs, 118,267 raster tiles and 320 Sunlight assets**. These two waves add 21 jobs and 137 tiles. Nineteen source-pixel-gap attempts were consumed and quarantined; they are not counted as accepted and are not replayed. Independent recovery confirmed output hashes/pixels, all new package chunks, and preservation of existing caches.

Modeled cumulative Cloud production is USD12.0334351710 against USD125. Modeled storage is USD0.7762299104/month against USD2/month. These are model settlements, not invoices. The controller's separate conservative GitHub reservation ledger and USD350 hard stop remain in force. Legacy initiation and source-writer fences remain active; no identities, roles or permanent credentials were added beyond the owner-executed exact provider-condition change.

Machine-readable proof is in `evidence/20261102/autonomy-two-live-waves.json`. It contains the exact source and plan hashes, dispatch nonces, run/job IDs, complete immutable recovery references, successor linkage and the observed continuation state.

## Further engineering completed during live production

[PR76](https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/76) adds an exact recovered-tile/native-package catalog adapter and a verified-child overview adapter using the unchanged pinned native renderer. Fifteen catalog integrity tests and five native overview tests pass, including missing/tampered dependency rejection and zero-network overview generation from preserved child bytes.

Three new full source windows also passed actual native raster validation, using original per-job source byte/request ceilings and the unchanged production mosaic engine. Hiking used a complete 512x512 window; Terrain used a complete 514x514 window including halo and per-source US-survey-foot-to-metre conversion; leaf-off used a complete 1024x1024 window. The latter two mosaicked two original public source objects. Evidence is preserved in `evidence/20261102/expanded-full-windows.json` on PR76. These results establish the tested windows, not catalog-wide pixel coverage or rights certification.

The new adapters and source validations do not alter an in-flight immutable source plan. Integration into protected production QA records and future overview/source allocations requires the normal reviewed source migration at a safe controller boundary. No accepted production source, tile, cache, receipt, package or spending safeguard was replaced.

## Remaining full-product work

Autonomous initiation and independent recovery are operational. Full approved geographic coverage, all required zooms/layers, expanded-source promotion, remaining overview production, final protected native delivery and physical iPhone airplane-mode acceptance remain incomplete. The controller must keep respecting source exhaustion and spending limits. Success of these two waves does not certify the complete offline-map product.
