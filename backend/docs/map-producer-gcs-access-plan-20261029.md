# Red River Gorge Hiker — isolated map-producer cloud access (PREPARED ONLY)

The old 141 MB `2026.10.08.1` package is already in the private
`rrgh-nonproduction-protected-packages` bucket and delivered through the
existing Firebase authorization backend. **Do not change this delivery path.**

## Verified blocker

On 2026-10-29, read-only Actions run 40875008121, on isolated engineering
branch `lane20/offline-production-preflight-20261029`, failed at Google
Workload Identity Federation with `unauthorized_client` and rejected branch
attribute condition. The old `github-deploy` principal is authorized for
`backend/phase-3-nonprod`; it has Firebase deployment privileges and MUST NOT
be reused by map production. Previous backend records also document that it
could not self-grant required IAM roles.

## Prepared replacement

- Separate WIF pool `rrgh-map-production` and GitHub OIDC provider
  `github-map-build`, in the EXISTING project (no new project/bucket).
- Direct WIF, no service account or persistent credential/secret.
- Provider condition pins GitHub repository ID 1325611891, owner ID 313924954,
  the exact engineering branch, `push` event, and exact single workflow.
- New managed folder prefix `engineering/map-production/` in existing bucket
  grants objectCreator + objectViewer only (no overwrite/delete).
- Managed folder prefix for accepted
  `packages/offline/gorge-base/2026.10.08.1/` grants objectViewer only.
  The sensitive `backend-secrets/` prefix and all other packages remain out
  of scope; no deployment or project-level permissions.
- Source-only setup script `backend/scripts/bootstrap_map_producer_wif.sh`
  defaults to PLAN ONLY and requires owner-authorized Google Cloud
  administrator credentials plus an explicit `--apply` switch and
  `RRGH_AUTHORIZE_IAM=YES_APPLY_LIMITED_PRODUCER`.
- Read-only nondeploying workflow template
  `.github/workflows/offline-map-producer-access.yml` authenticates from
  the EXACT approved engineering branch; first verifies accepted Base object
  metadata is readable and signing keyring access is denied. Does not
  download protected bytes or publish GCS objects.

## Next gate

An authorized Cloud administrator must apply/review these IAM changes in a
short-lived session. Existing GitHub connector and `github-deploy` credential
cannot administer Google IAM. The Work cloud browser may carry out that
owner-authorized administrative action; if Google requires interactive owner
authentication, only that minimum owner action should be requested.

Afterward, transplant the workflow to the approved producer branch and run
ONE read-only CI identity check, read its logs, inspect costs and deny attempts,
then run a separately capped immutable staging/resume drill. Continue full
Gorge production ONLY after source-cache/whole-region cost forecast and actual
GCS checkpoint viability have been verified. Never dispatch deployment,
merge protected PRs, expose route data or request early iPhone testing.

Authoritative source: Lane20/21 revision4 report and Activity Log row804.

## Execution review, 2026-10-29

The original plan-only mode and Bash syntax check pass. Before administrative
execution, the reviewed continuation corrects the bucket metadata call to
`--raw` (the CLI otherwise returns standardized fields), adds checkout before
Google authentication, and requires an explicit permission-denied result for
the signing-key negative test. Project-number, unexpected-provider and custom
audience checks fail closed. These changes do not broaden any grant.

The Cloud Browser currently returns `Site Unavailable` at the requested
Google Cloud Console project, including after one reload. No authenticated
administrator session or live Google IAM state can be verified here. No IAM
apply, metadata CI or staging write has been performed. The exact owner-only
step is running the reviewed, commit-pinned bootstrap once in the existing
authenticated administrator Cloud Shell session. Then engineering can place
the workflow on its exact approved producer branch and inspect the results.

Do not equate the offline command fixtures with live cloud authorization.

