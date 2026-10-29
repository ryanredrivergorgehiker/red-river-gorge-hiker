#!/usr/bin/env bash
# Correct only the map-producer OIDC subject mapping after GitHub run 40902826243.
# No permissions, branch conditions, service accounts, or bucket settings change.
set -euo pipefail
PROJECT=rrgh-nonproduction
NUMBER=843975209563
POOL=rrgh-map-production
PROVIDER=github-map-build
BRANCH=lane20/offline-production-preflight-20261029
WORKFLOW=offline-map-producer-access.yml
REF="ryanredrivergorgehiker/red-river-gorge-hiker/.github/workflows/$WORKFLOW@refs/heads/$BRANCH"
CONDITION="assertion.repository_id=='1325611891' && assertion.repository_owner_id=='313924954' && assertion.ref=='refs/heads/$BRANCH' && assertion.event_name=='push' && assertion.workflow_ref=='$REF'"
OLD=assertion.sub
NEW="assertion.repository_id+':'+assertion.ref"
MAPPING="google.subject=$NEW,attribute.repository_id=assertion.repository_id"

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--plan" && "$1" != "--apply" ) ]]; then
  echo 'Usage: script [--plan|--apply]' >&2; exit 2
fi
ACTION="--plan"
if [[ $# -eq 1 ]]; then ACTION="$1"; fi
if [[ "$ACTION" == "--apply" && "$(printenv RRGH_AUTHORIZE_SUBJECT_FIX 2>/dev/null || true)" != "YES_LIMITED_MAPPING_ONLY" ]]; then
  echo 'Refusing: explicit authorization missing.' >&2; exit 2
fi
command -v gcloud >/dev/null
command -v python3 >/dev/null
[[ "$(gcloud config get-value project 2>/dev/null)" == "$PROJECT" ]] || { echo 'Wrong project.' >&2; exit 3; }
[[ "$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')" == "$NUMBER" ]] || { echo 'Wrong project number.' >&2; exit 3; }
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
get_state() {
  gcloud iam workload-identity-pools providers describe "$PROVIDER" \
    --project="$PROJECT" --location=global --workload-identity-pool="$POOL" --format=json > "$TEMP/provider.json"
  gcloud iam workload-identity-pools providers list \
    --project="$PROJECT" --location=global --workload-identity-pool="$POOL" --format=json > "$TEMP/providers.json"
}
validate() {
  RRGH_EXPECTED_CONDITION="$CONDITION" RRGH_OLD_SUBJECT="$OLD" RRGH_NEW_SUBJECT="$NEW" \
    python3 - "$TEMP/provider.json" "$TEMP/providers.json" "$1" <<'PY'
import json,os,sys
p=json.load(open(sys.argv[1]))
providers=json.load(open(sys.argv[2]))
assert len(providers)==1 and providers[0]["name"].endswith("/providers/github-map-build"), "Unexpected extra provider"
assert p.get("attributeCondition")==os.environ["RRGH_EXPECTED_CONDITION"], "Branch/workflow restriction unexpectedly changed"
assert p.get("oidc",{}).get("issuerUri")=="https://token.actions.githubusercontent.com", "Issuer mismatch"
assert not p.get("disabled",False), "Provider disabled"
assert not p.get("oidc",{}).get("allowedAudiences"), "Custom audience detected"
mapping=p.get("attributeMapping",{})
assert mapping.get("attribute.repository_id")=="assertion.repository_id", "Repository mapping changed"
assert set(mapping)=={"google.subject","attribute.repository_id"}, "Unexpected identity mapping"
old,new=os.environ["RRGH_OLD_SUBJECT"],os.environ["RRGH_NEW_SUBJECT"]
actual=mapping.get("google.subject")
assert actual in (old,new), "Unrecognized subject mapping; STOP"
if sys.argv[3]=="after":
    assert actual==new, "Subject mapping was not updated"
print("Validated pool/provider; exact branch/workflow condition preserved; subject:",actual)
PY
}
get_state
validate before
echo 'Proposed update: ONLY google.subject from long GitHub assertion.sub to short repository ID + exact ref.'
echo 'Managed-folder grants, existing deployment identity, provider condition and bucket remain unchanged.'
if [[ "$ACTION" != "--apply" ]]; then
  echo 'PLAN ONLY; no Google Cloud changes. Apply requires explicit authorization.'
  exit 0
fi
gcloud iam workload-identity-pools providers update-oidc "$PROVIDER" \
  --project="$PROJECT" --location=global --workload-identity-pool="$POOL" \
  --attribute-mapping="$MAPPING" --quiet >/dev/null
get_state
validate after
echo 'MAPPING FIX COMPLETE. Re-run existing read-only GitHub producer identity preflight.'
