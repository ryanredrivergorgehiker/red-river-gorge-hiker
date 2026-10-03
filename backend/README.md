# Red River Gorge Hiker — Firebase / Backend & Entitlements

Status: **PHASE 2 / LOCAL EMULATOR PROTOTYPE**

This directory is intentionally isolated from the production Website build. It implements the frozen Lane 20 account/trial/entitlement contract against the Firebase Local Emulator Suite only.

## Safety boundary

- Uses the demo project ID `demo-rrgh-entitlements`.
- Creates no real Firebase project or Google Cloud resource.
- Does not require Blaze.
- Does not deploy Functions.
- Does not provision Cloud Storage.
- Contains no protected route geometry.
- Contains no user-recorded-track upload, sync, storage, or API.
- Firestore client rules deny all direct reads and writes.
- Store purchase validation remains an internal emulator test seam until LEG-Q-0020.
- Protected package delivery returns authorization metadata only; no package URL exists until LEG-Q-0018 is cleared.

Firebase recommends demo projects for emulator-only work because they have no live resources and accidental calls to non-emulated services fail instead of reaching production.

## Frozen entitlement semantics represented here

Canonical entitlements:

- `base`
- `backpacking`
- `off_trail`

`day_hikes` is derived from Base and is not separately purchased.

A validated Apple or Google Play purchase maps to the same canonical RRGH account entitlement. Store/platform evidence stays separate from canonical entitlement state. More than one store-evidence record may support the same entitlement.

The seven-day Base trial is one-time at the RRGH account level. Trial access unlocks Base/Day Hikes only and does **not** satisfy the permanent-Base prerequisite for Backpacking or Off-Trail.

## Shared callable API

One callable Function, `rrghAccountApi`, dispatches only these Phase 2 operations:

- `getAccountState`
- `startBaseTrial`
- `getEntitlements`
- `authorizeProtectedPackage`
- `initiateAccountDeletion`

There is intentionally no customer operation for granting/revoking entitlements and no track-related operation.

## Run locally

Requirements:

- Node.js 22
- Java 21 or later
- npm

From this `backend` directory:

```bash
npm install --prefix functions --no-audit --no-fund
npx --yes firebase-tools@15.30.2 emulators:exec \
  --project demo-rrgh-entitlements \
  --only auth,firestore,functions \
  "npm --prefix functions test"
```

The integration suite exercises Authentication, Firestore and Functions emulators together. No Firebase login or real project is required.

## Deliberately deferred

- Real Firebase/Google Cloud project creation.
- Blaze billing.
- Cloud Storage package delivery.
- App Check enforcement.
- Production origins/region/quotas/rate limits.
- Apple/Google store-server validation and notification handling.
- Final account-deletion purge/retention mechanics.
- Sign-in provider UX beyond the backend requirement for an authenticated Firebase user.
- LEG-Q-0018, LEG-Q-0019 and LEG-Q-0020 implementation details.
