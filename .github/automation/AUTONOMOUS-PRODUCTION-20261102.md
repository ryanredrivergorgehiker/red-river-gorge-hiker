# Historical deployment record — administrative block resolved

**Current status:** the owner applied the reviewed Cloud update, the new identity passed authenticated readback, and two consecutive automatic production executions passed independent recovery. See [the live proof](AUTONOMY-PROOF-20261102.md). The earlier administrator action and unverified-execution statements below describe the pre-upgrade snapshot, not a current blocker.

The owner authorized the exact restricted `workflow_dispatch` identity on 2026-11-02. The old no-IAM-change restriction is superseded for this one reviewed provider-condition change. This record supersedes the earlier cutover-not-activated report for controller deployment; it does not claim product or live production completion.

## Deployed engineering

- Controller PR: https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/pull/75 (merged).
- Reviewed controller commit: `c55bfb72790beea4b6f38e18a0a3ea62a0e862ec` on `lane20/offline-production-preflight-20261029`.
- Production source commit: `444fa31cab3e321bc6e93b32b315efaba1ed24cd` on `lane20/map-producer-iam-design-20261029`.
- Legacy source writer fenced at `812281c59e22ffaffe1f07b9355b810f464cf8eb` on `lane20/unattended-supervisor-20261031`.
- All five jobs in the old producer workflow are disabled. The legacy push identity remains present in the reviewed Cloud condition. The new source guard rejects legacy initiation while the durable controller owner is `autonomous-v1`.
- The dispatcher checks exact source leases and the hashes of both legacy fences, records a compare-and-swap claim before dispatch, rejects duplicate/ambiguous launches, and binds each source process to the exact run, nonce, source commit, plan and epoch.
- Separate recovery runners verify outputs before successor publication. Successor dispatch uses the ephemeral repository `GITHUB_TOKEN`; no permanent credentials or new service accounts were introduced.
- Existing USD125 Cloud and USD2/month storage safeguards remain. GitHub reservations conservatively carry the last USD281.53 observation, add USD5 engineering reserve, USD0.10 per probe and USD5 per production dispatch, and stop at USD350. This is reservation accounting, not a fresh billing statement.

## Executed validation and live evidence

- Map QA passed: https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41489062705
- 18 dispatcher/identity/race/budget tests plus 40 immutable checkpoint and selective-cache recovery tests passed.
- The real processing engine validated the new Wave058 plan, including source snapshots, quality profiles, resource reservations and budget admission: 20 jobs, 180 tiles, USD0.6456 maximum incremental Cloud reservation.
- Two synthetic offline successor cycles passed (58 to 59, then 59 to 60). These are software tests, not live production evidence.
- Owner-authenticated launcher: https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41489288461
- Actual automatically initiated `github-actions[bot]` dispatch: https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/actions/runs/41489346851
- The `admit` job succeeded and persisted ownership. The Cloud authentication action then returned `unauthorized_client`: `The given credential is rejected by the attribute condition.`
- Producer, recovery and advancement jobs were skipped. The failure handler recorded `auth-required`; there were no production Cloud writes and Wave058 was not consumed.
- Current prepared plan: `6429b4b90671b522993a84b255f75fee33a37d39206d09a2119f6bee1177f8c4`. The prior prepared Wave058 plan and all historical accepted plans remain unchanged.
- Latest accepted checkpoint remains Wave057: 11,144 jobs, 118,130 raster tiles, 320 Sunlight assets. Receipt SHA256 `ec01fd3837dab8f0eb1a3a0dd4d45b44cde0d621d60c0b92afe32cf7f48a60ea`, generation `1793626999921506`.

## One administrator action

This session has no configured Google Cloud administrator credential or available Cloud admin connector; the Cloud console is inaccessible in its browser. No Cloud IAM change was attempted. The STS error is evidence of the rejected dispatch identity, not a readback of the complete live provider policy.

Run the following in the existing authorized administrator's Google Cloud Shell. The pinned reviewed script reads and verifies the current project, project number, provider set, issuer, audiences, mappings and exact condition **before** any update. It refuses unknown policy drift, changes only the exact provider condition, preserves the original push identity, and verifies the result. It adds no IAM roles, service accounts, keys or bucket permissions.

```bash
set -euo pipefail
gcloud config set project rrgh-nonproduction
rrgh_script="$(mktemp)"
curl --fail --silent --show-error --location \
  'https://raw.githubusercontent.com/ryanredrivergorgehiker/red-river-gorge-hiker/c55bfb72790beea4b6f38e18a0a3ea62a0e862ec/backend/scripts/upgrade_map_producer_wif_20261031.sh' \
  --output "$rrgh_script"
printf '%s  %s\n' '72604c5e22aa17815b5cf530026786092b0673f8759b3807d528c86118a8b443' "$rrgh_script" | sha256sum --check
RRGH_AUTHORIZE_AUTONOMOUS_WIF=YES_LIMITED_WORKFLOW_DISPATCH bash "$rrgh_script" --apply
```

## Resume and verify

After the administrator action succeeds, the engineering agent should read the current owner state, source head and active runs, then make one owner-authenticated update to `.github/automation/rrgh-controller-request.json` on the worker branch. Do not rerun the failed Actions execution or reset/refund its durable record. A fresh launch counter and nonce will run a new read-only authentication probe; success automatically initiates production.

The live probe must recover and hash the exact Wave057 receipt, verify its carry, and prove both the old/new Wave058 bootstrap claims and shared campaign sequence fence are absent. Each production wave then requires successful independent recovery before automatic advancement. Collect two consecutive real production run IDs and their independent recovery receipts; these remain outstanding.

To pause new work, set `enabled` to false in the owner record using a fresh GitHub contents SHA. Existing independent recovery remains permitted. Never clear a `dispatching`, `running`, `publishing` or `halted` record merely to retry: reconcile actual Actions and immutable Cloud claims first. Never restore the old source writer or producer alongside the new owner.

## Remaining map completion work

The source expansion, exact geographic inventory, overview dependency queue and package readiness engineering in PR74 remains separate from this authentication cutover. Its existing pixel, native-resolution, halo/edge, rights, provenance and physical-device gates remain in force. The automatic source planner still selects only reviewed existing source windows; it stops on exhaustion rather than inventing coverage or replaying excluded attempts. Expanded-source promotion, overview production, final package delivery and physical-device acceptance are not claimed complete by this deployment.
