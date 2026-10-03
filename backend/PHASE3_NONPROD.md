# Lane 20 — Phase 3 non-production Firebase environment

Status: **OWNER APPROVED / CODE READY / CLOUD PROJECT NOT YET CREATED**

## Fixed non-production design

- Firebase / Google Cloud project: one dedicated non-production project.
- Firestore: Standard edition, one database, regional location `us-east5` (Columbus).
- Cloud Functions for Firebase: 2nd gen callable `rrghAccountApi`, region `us-east5`.
- Function scaling: `minInstances: 0`, `maxInstances: 2`.
- Function resources: 256 MiB, `gcf_gen1` CPU allocation, 15-second timeout.
- Authentication: project resource may be created now; production sign-in provider UX remains unresolved. Do not enable social providers merely because they exist.
- App Check: register/observe in non-production before enforcement. Enforcement stays off initially.
- Firestore rules: direct customer client reads/writes remain deny-all; trusted Function/Admin SDK is authoritative.
- Cloud Storage: **do not create a bucket in this Phase 3 step**. LEG-Q-0018 is resolved for source rights, but package-generation/compliance implementation should be completed before protected bytes are uploaded.
- No Website production changes.
- No App Store / Google Play products.
- No customer accounts except controlled test accounts.
- No user-track upload/sync/server storage API.

## Why us-east5

The product is aimed initially at the Red River Gorge / eastern United States audience. Firebase currently supports both Cloud Firestore and 2nd-gen Cloud Functions in `us-east5` (Columbus). A regional Firestore location is lower-cost than multi-region and gives low latency when co-located with the Function. Firestore location is immutable after database creation, so this must be selected deliberately.

## Cost controls to configure immediately after Blaze is linked

1. Create an all-services monthly **alerts-only budget of $5** for this non-production project.
2. Configure alert thresholds at 20%, 50%, 80%, and 100%.
3. Configure a **Cloud Functions spend cap of $5/month** if the current Firebase console offers it for the project.
4. Keep `rrghAccountApi` at `minInstances: 0` and `maxInstances: 2`.
5. Do not enable Firestore PITR, scheduled backups, TTL deletes, App Hosting, Extensions, AI products, Cloud Run services, or Storage.
6. Review billing/usage after initial deployment and again after the first integration test.

A budget alert does not stop charges. Firebase's current spend-cap feature for Cloud Functions can pause new function usage when the configured threshold is reached, but enforcement can lag and is not a guaranteed hard cap.

## Owner console handoff

The owner must use the Firebase console because creating the project and linking Blaze requires the owner's Google/Cloud Billing identity and, if no billing account exists, a payment method. ChatGPT must not invent or handle payment credentials.

The first owner action is simply:

1. Open the Firebase console while signed into the Google account that should own RRGH's Firebase project.
2. Choose **Add project / Create a Firebase project**.
3. Stop before completing the wizard if the console asks for a project name/ID choice that differs materially from the planned non-production naming convention.

No payment is required merely to open the console or start creating the project. Blaze/billing is a later explicit screen in this same setup sequence.

## Planned naming

Preferred display name: `RRGH Nonproduction`

Preferred project ID pattern: `red-river-gorge-hiker-nonprod`

Project IDs are globally unique, so Firebase may require a suffix. Any accepted ID must clearly contain `nonprod`; record the exact ID before deployment.

## Deployment sequence after project creation

1. Record exact Firebase project ID and Google Cloud project number.
2. Link Blaze billing.
3. Immediately configure the $5 alerts-only budget and the Functions $5 spend cap if available.
4. Create Firestore Standard in `us-east5`.
5. Enable only the minimum Authentication configuration needed for controlled testing.
6. Deploy Firestore deny-all rules and `rrghAccountApi` only.
7. Create one controlled test account.
8. Run remote non-production contract tests.
9. Register App Check clients and observe metrics before enforcement.
10. Do not create Storage until the offline package implementation is ready for LEG-DEC-0033 compliance testing.
