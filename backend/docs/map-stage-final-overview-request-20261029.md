# One remaining terrain overview: measured exception request

Run 40990810532 consumed all twelve authorized raster attempts. Eleven jobs (107 images, 3,122,969 bytes) have durable job receipts. Independent recovery succeeded for those images, all new cache packs, 68 baseline/shared files and 22 SQLite snapshots; 161 adjacent edges were measured. The final job, `terrain-15-8772-12661`, has no durable output/job receipt and is not accepted as complete.

The stage reached checkpoint preservation after the final native worker returned. The next write was rejected with HTTP 412. Its 384,676-byte request body and the unchanged ledgers after two source-free overview jobs identify the identical-state-pack collision: content-addressed `Slot.put` attempted to create the same object twice. The failed request and its reservation remain in the audit. No production job was retried. The runner was cleaned up, and no saved copy of the last tile is available.

The source fix reuses only a content-addressed object already positively created and checksum-confirmed in the same live slot. It does not probe remote objects, catch/retry HTTP 412, reopen claims, erase failures or refund reservations. Four focused offline tests passed, including the two-overview sequence with identical ledger bytes and distinct catalog paths. This repair is source-only; the consumed plan and workflow are unchanged.

## Single requested exception

Authorize one additional attempt for `terrain-15-8772-12661` only, raising this stage's cumulative attempt ceiling from 12 to 13. Keep the $0.35 stage release, $7.65 locked balance and every other original ceiling unchanged. The only required owner action is approval of this attempt exception; no account authentication or file movement is needed.

Proposed immutable recovery allocation: 1 MiB new storage, 2 MiB GCS reads, eight Class A operations, forty Class B operations, zero official-source transfer/requests, six minutes and one worker, including independent recovery. Use the four already accepted z16 terrain children (89,547 bytes total); do not transfer the seed again, reread the Base, render any completed tile or change image quality. Maximum modeled incremental Cloud cost is below $0.001; reserve $0.002 within the existing release.

All historical claims, receipts, consumption and failed-operation reservations remain. Keeping the current cumulative byte reservations and adding 2 MiB produces 1,073,605,499 read bytes, below the original 1,073,741,824 limit by 136,325 bytes. Eight additional Class A reservations reach the original 200 ceiling. Reconcile only demonstrably unused closed Class B reservations under the already approved stage-specific policy. The extra raster attempt is the only requested limit change. The recovery plan remains nonexecutable until that approval is recorded and bound to its exact source.

Current cumulative stage usage: 95 stored objects / 552,053,355 bytes; 945,441,700 response bytes; 115 Class A and 263 Class B HTTP operations. Estimated first-month cost is $0.219354768 gross or $0.263225722 with 20% contingency; incremental retained storage is $0.018509031/month with contingency. These are metered estimates, not current billing readings. No remaining campaign funds have been released.
