#!/usr/bin/env bash
# RRGH 2026-10-31: ADD ONLY the exact restricted GitHub Actions dispatch identity.
# Preserves the original push identity, short mapped subject and all IAM roles.
# Requires user-authenticated Google Cloud administrator Cloud Shell. Plan by default.
set -euo pipefail
PROJECT=rrgh-nonproduction
NUMBER=843975209563
POOL=rrgh-map-production
PROVIDER=github-map-build
BRANCH=lane20/offline-production-preflight-20261029
BASE="assertion.repository_id=='1325611891' && assertion.repository_owner_id=='313924954' && assertion.ref=='refs/heads/$BRANCH' && "
PUSHREF="ryanredrivergorgehiker/red-river-gorge-hiker/.github/workflows/offline-map-producer-access.yml@refs/heads/$BRANCH"
DISPATCHREF="ryanredrivergorgehiker/red-river-gorge-hiker/.github/workflows/offline-map-restricted-dispatch.yml@refs/heads/$BRANCH"
OLD="${BASE}assertion.event_name=='push' && assertion.workflow_ref=='$PUSHREF'"
NEW="${BASE}((assertion.event_name=='push' && assertion.workflow_ref=='$PUSHREF') || (assertion.event_name=='workflow_dispatch' && assertion.workflow_ref=='$DISPATCHREF'))"
SUBJECT="assertion.repository_id+':'+assertion.ref"
ACTION="${1:---plan}"
if [[ $# -gt 1 || ( "$ACTION" != "--plan" && "$ACTION" != "--apply" ) ]]; then
  echo 'Usage: upgrade_map_producer_wif_20261031.sh [--plan|--apply]' >&2
  exit 2
fi
if [[ "$ACTION" == "--apply" && "${RRGH_AUTHORIZE_AUTONOMOUS_WIF:-}" != "YES_LIMITED_WORKFLOW_DISPATCH" ]]; then
  echo 'Explicit limited IAM administrator authorization missing. Refusing.' >&2
  exit 2
fi
command -v python3 >/dev/null
command -v gcloud >/dev/null
[[ "$(gcloud config get-value project 2>/dev/null)" == "$PROJECT" ]] || {
  echo 'Wrong Google Cloud project.' >&2; exit 3;
}
[[ "$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')" == "$NUMBER" ]] || {
  echo 'Wrong Google Cloud project number.' >&2; exit 3;
}
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
get_state() {
  gcloud iam workload-identity-pools providers describe "$PROVIDER" \
    --project="$PROJECT" --location=global --workload-identity-pool="$POOL" \
    --format=json > "$TEMP/provider.json"
  gcloud iam workload-identity-pools providers list \
    --project="$PROJECT" --location=global --workload-identity-pool="$POOL" \
    --format=json > "$TEMP/providers.json"
}
check_state() {
  RRGH_EXPECT_OLD="$OLD" RRGH_EXPECT_NEW="$NEW" RRGH_EXPECT_SUBJECT="$SUBJECT" \
    python3 - "$TEMP/provider.json" "$TEMP/providers.json" "$1" <<'PY'
import json, os, sys
with open(sys.argv[1]) as f: p=json.load(f)
with open(sys.argv[2]) as f: providers=json.load(f)
assert len(providers)==1 and providers[0]['name'].endswith('/providers/github-map-build'), 'Unknown providers: STOP'
assert p.get('oidc',{}).get('issuerUri')=='https://token.actions.githubusercontent.com', 'Issuer changed: STOP'
assert not p.get('disabled',False), 'Provider is disabled: STOP'
assert not p.get('oidc',{}).get('allowedAudiences'), 'Unexpected audiences: STOP'
m=p.get('attributeMapping',{})
assert set(m)=={'google.subject','attribute.repository_id'}, 'Unknown mapped attributes: STOP'
assert m['google.subject']==os.environ['RRGH_EXPECT_SUBJECT'], 'Short identity mapping changed: STOP'
assert m['attribute.repository_id']=='assertion.repository_id', 'Repository mapping changed: STOP'
old,new=os.environ['RRGH_EXPECT_OLD'],os.environ['RRGH_EXPECT_NEW']
actual=p.get('attributeCondition')
assert actual in (old,new), 'Provider condition differs from the reviewed exact policy: STOP'
if sys.argv[3]=='after': assert actual==new, 'Exact reviewed new condition not applied: STOP'
print('RRGH WIF provider verified; condition state:', 'original' if actual==old else 'reviewed dual-identity')
PY
}
get_state
check_state before
echo 'Scope: preserve owner/repository/branch checks; retain exact push workflow;'
echo 'allow only the same-branch restricted workflow_dispatch worker.'
echo 'No service account, IAM grant, secret, extra project, storage role, key or bucket change.'
if [[ "$ACTION" == "--plan" ]]; then
  echo 'PLAN ONLY. No Google Cloud changes.'
  exit 0
fi
ACTUAL="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["attributeCondition"])' "$TEMP/provider.json")"
if [[ "$ACTUAL" == "$NEW" ]]; then
  echo 'Already at exact reviewed policy; no write.'
  exit 0
fi
[[ "$ACTUAL" == "$OLD" ]] || { echo 'Unexpected existing policy: STOP' >&2; exit 4; }
gcloud iam workload-identity-pools providers update-oidc "$PROVIDER" \
  --project="$PROJECT" --location=global --workload-identity-pool="$POOL" \
  --attribute-condition="$NEW" --quiet >/dev/null
get_state
check_state after
echo 'COMPLETE: existing push WIF kept; exact restricted workflow_dispatch identity enabled.'
