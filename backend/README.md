# Red River Gorge Hiker — Firebase / Backend & Entitlements

Status: **PHASE 3 NON-PRODUCTION / PROTECTED DELIVERY IMPLEMENTATION**

This directory implements the Lane 20 account/trial/entitlement contract against the Firebase Emulator Suite and the controlled `rrgh-nonproduction` project. It is isolated from the production Website build.

## Safety boundary

- Production Firebase is not authorized or created.
- Firestore direct-client rules remain deny-all.
- Firebase Storage direct-client rules remain deny-all.
- The nonproduction package bucket is private, uniform-access, and public-access-prevention protected.
- Protected/offline package bytes are read only by the server runtime and delivered through `rrghPackageDownload`.
- No permanent Firebase download token is created.
- No signed/object URL is persisted in Firestore or logs.
- App Check enforcement remains OFF pending the governed Apple Team-ID/client-observation gate.
- No user-recorded-track upload, sync, storage, collection, or server API exists.
- Real protected route bytes never enter GitHub; GitHub contains only package metadata, exact integrity expectations, build code, and unmistakably synthetic test fixtures.

## Canonical entitlement semantics

Canonical entitlements:

- `base`
- `backpacking`
- `off_trail`

`day_hikes` derives from Base and is not separately purchased.

The seven-day Base trial is one-time at the RRGH-account level. Trial access unlocks Base/Day Hikes only. It does **not** satisfy the permanent-Base prerequisite for Backpacking or Off-Trail.

Validated Apple or Google Play evidence maps to the same canonical RRGH entitlement. Store evidence stays separate from entitlement state. More than one valid evidence record may support one entitlement.

## Callable account API

`rrghAccountApi` dispatches only:

- `getAccountState`
- `startBaseTrial`
- `getEntitlements`
- `authorizeProtectedPackage`
- `initiateAccountDeletion`

There is no customer operation for granting/revoking entitlements and no track-related operation.

## Protected package delivery v2

`authorizeProtectedPackage(packageId)` requires an authenticated Firebase user and always re-derives the current server-authoritative account/access state.

Ready authorization returns additive package metadata:

- `package.packageId`
- `package.packageType`
- `package.version`
- `package.sha256`
- `package.byteCount`
- `package.requiredEntitlement`
- `package.offlineManifest` for `gorge-base`

Ready delivery returns:

- `delivery.ready = true`
- `delivery.reason = null`
- `delivery.method = "capability_https"`
- `delivery.httpMethod = "GET"`
- `delivery.url` = the stable `rrghPackageDownload` HTTPS endpoint, with no capability in the URL
- `delivery.expiresAt`
- `delivery.authorizationScheme = "Bearer"`
- `delivery.authorizationToken` = a random opaque short-lived capability

The capability TTL is five minutes. Only its SHA-256 hash is stored. The download endpoint re-checks package version/object, current account status, and current entitlement before streaming the exact private object. Expiration requires reauthorization.

Stable unavailable/error reasons include:

- `package_not_found`
- `package_not_ready`
- `package_superseded`
- `package_configuration_invalid`
- `not_entitled`
- `account_not_active`
- `package_object_unavailable`
- `package_object_mismatch`
- `delivery_capability_invalid`
- `delivery_capability_expired`
- `backend_temporarily_unavailable`

## Frozen initial package IDs

- `route-rte-0001` — version `1` — RTE-0001 Skybridge Arch — `base`
- `route-rte-0002` — version `1` — RTE-0002 Princess Arch — `base`
- `gorge-base` — version `2026.10.06.1` — governed offline base archive — `base`

There is no currently approved Backpacking or Off-Trail route package because Lane 19 has not approved such a route for publication. The entitlement machinery is nevertheless tested with synthetic nonproduction fixtures.

## Governed package sources

The two real route package files are read during deployment from the privately shared Lane 19 Drive authority by the keyless nonproduction deploy identity. Exact byte counts and Route Register SHA-256 values are verified before upload. Those bytes are never committed to GitHub.

The Gorge Base builder creates a fixed-version archive from the legally governed source families under LEG-DEC-0033:

- KyFromAbove terrain/hillshade export
- USGS NHDPlus High Resolution hydrography snapshot
- 2026 Census TIGER/Line county roads
- bounded USDA Forest Service trail/road/basic-ownership snapshots
- fixed Geofabrik Kentucky OpenStreetMap snapshot, locally clipped/transformed with ODbL notice
- Kentucky Geological Survey oil/gas well dataset, clipped/transformed with provider documentation and modification notice

The package intentionally does not fabricate or substitute:

- protected RRGH route geometry (separate route packages)
- StreamStats offline data (connected-only)
- parcel/private-property data (source not yet authorized/frozen)
- Gaia/CalTopo/proprietary basemap content
- public OSM tile scraping or public Overpass as a paid delivery backend
- static weather represented as current/live data

The generated external manifest matches Lane 21 `OfflinePackageManifest` exactly and records source URL/provider/vintage or retrieval time/AOI or source objects/processing method/rights basis/attribution or disclaimer/output version/per-source SHA-256 plus final archive byte count and SHA-256.

## Emulator validation

Requirements:

- Node.js 22
- Java 21+
- npm

From `backend`:

```bash
npm install --prefix functions --no-audit --no-fund
npx --yes firebase-tools@15.30.2 emulators:exec \
  --project demo-rrgh-entitlements \
  --only auth,firestore,functions,storage \
  "npm --prefix functions test"
```

The emulator suite uses only synthetic protected-package bytes. It verifies entitlement gates, exact-byte retrieval, manifest shape, unavailable/superseded states, capability expiry, deletion-pending denial, and deny-all client storage/firestore boundaries.

## Remaining production/store gates

- Apple Team ID / final App Attest enrollment and observed-client traffic before enforcement.
- LEG-Q-0020 Apple/Google store product, restore/refund/revocation, final account-deletion, privacy/store-submission configuration.
- Production package bucket/environment and production traffic are not authorized.
