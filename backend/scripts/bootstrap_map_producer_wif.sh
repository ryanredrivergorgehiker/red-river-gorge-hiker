#!/usr/bin/env bash
# One-time keyless direct-WIF authorization. Defaults to PLAN ONLY.
# google.subject uses short GitHub repository-id + ref (OIDC sub exceeds 127 bytes).
set -euo pipefail
PROJECT=rrgh-nonproduction
NUMBER=843975209563
BUCKET=rrgh-nonproduction-protected-packages
POOL=rrgh-map-production
PROVIDER=github-map-build
REPO_ID=1325611891
OWNER_ID=313924954
BRANCH=lane20/offline-production-preflight-20261029
WORKFLOW=offline-map-producer-access.yml
WORKFLOW_REF="ryanredrivergorgehiker/red-river-gorge-hiker/.github/workflows/$WORKFLOW@refs/heads/$BRANCH"
CONDITION="assertion.repository_id=='$REPO_ID' && assertion.repository_owner_id=='$OWNER_ID' && assertion.ref=='refs/heads/$BRANCH' && assertion.event_name=='push' && assertion.workflow_ref=='$WORKFLOW_REF'"
MAPPING="google.subject=assertion.repository_id+':'+assertion.ref,attribute.repository_id=assertion.repository_id"
MEMBER="principalSet://iam.googleapis.com/projects/$NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository_id/$REPO_ID"
STAGING="gs://$BUCKET/engineering/map-production/"
LEGACY="gs://$BUCKET/packages/offline/gorge-base/2026.10.08.1/"
echo "Existing project: $PROJECT; bucket: $BUCKET"
echo "Isolated direct WIF: $POOL/$PROVIDER; repo ID $REPO_ID; owner ID $OWNER_ID"
echo "Allowed branch: $BRANCH; workflow: $WORKFLOW; push only"
echo "Read+CREATE (not overwrite/delete): $STAGING"
echo "Read ONLY: $LEGACY"
echo "Excluded: backend-secrets, Firebase deployment, other packages, IAM admin."
if [[ $# -eq 0 || "$1" == "--plan" ]]; then echo 'PLAN ONLY; no cloud action.'; exit 0; fi
if [[ $# -ne 1 || "$1" != "--apply" || "$(printenv RRGH_AUTHORIZE_IAM 2>/dev/null || true)" != "YES_APPLY_LIMITED_PRODUCER" ]]; then
  echo 'Refusing; --apply plus exact administrative authorization are required' >&2; exit 2
fi
command -v gcloud >/dev/null
command -v python3 >/dev/null
[[ "$(gcloud config get-value project 2>/dev/null)" == "$PROJECT" ]] || { echo 'Wrong GCP project' >&2; exit 3; }
[[ "$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')" == "$NUMBER" ]] || { echo 'Wrong GCP project number' >&2; exit 3; }
REVIEW_DIR="$(mktemp -d)"
trap 'rm -rf "$REVIEW_DIR"' EXIT
# --raw is required: the CLI normally standardizes IAM fields into flat keys.
gcloud storage buckets describe "gs://$BUCKET" --project="$PROJECT" --raw --format=json |
  python3 -c 'import sys,json; x=json.load(sys.stdin); c=x.get("iamConfiguration",x.get("iam_configuration",{})); u=c.get("uniformBucketLevelAccess",c.get("uniform_bucket_level_access",{})); p=c.get("publicAccessPrevention",c.get("public_access_prevention","")); assert u.get("enabled") is True and p == "enforced", "Existing bucket protection absent"'
if ! gcloud iam workload-identity-pools describe "$POOL" --project="$PROJECT" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL" --project="$PROJECT" --location=global --display-name='RRGH isolated map production' --description='Nondeploying keyless GitHub map processing'
fi
# A different provider in the same pool could mint the same mapped principal.
gcloud iam workload-identity-pools providers list --project="$PROJECT" --location=global --workload-identity-pool="$POOL" --format=json > "$REVIEW_DIR/providers.json"
python3 -c 'import json,sys; rows=json.load(open(sys.argv[1])); assert all(p["name"].rsplit("/",1)[-1]==sys.argv[2] for p in rows), "Unexpected provider in dedicated pool; STOP"' "$REVIEW_DIR/providers.json" "$PROVIDER"
if gcloud iam workload-identity-pools providers describe "$PROVIDER" --project="$PROJECT" --location=global --workload-identity-pool="$POOL" --format=json > "$REVIEW_DIR/provider.json" 2>/dev/null; then
  RRGH_EXPECTED_CONDITION="$CONDITION" RRGH_EXPECTED_SUBJECT="assertion.repository_id+':'+assertion.ref" python3 -c 'import json,os,sys; p=json.load(open(sys.argv[1])); assert p.get("attributeCondition")==os.environ["RRGH_EXPECTED_CONDITION"] and p.get("oidc",{}).get("issuerUri") in ("https://token.actions.githubusercontent.com","https://token.actions.githubusercontent.com/") and not p.get("disabled",False), "Existing provider differs; STOP"; m=p.get("attributeMapping",{}); assert m.get("google.subject")==os.environ["RRGH_EXPECTED_SUBJECT"] and m.get("attribute.repository_id")=="assertion.repository_id", "Existing mapping differs"; assert not p.get("oidc",{}).get("allowedAudiences"), "Unexpected custom audiences; STOP"' "$REVIEW_DIR/provider.json"
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --project="$PROJECT" --location=global --workload-identity-pool="$POOL" --issuer-uri='https://token.actions.githubusercontent.com' --attribute-mapping="$MAPPING" --attribute-condition="$CONDITION" --display-name='RRGH bounded map build'
fi
for path in "$STAGING" "$LEGACY"; do
  if ! gcloud storage managed-folders describe "$path" --project="$PROJECT" >/dev/null 2>&1; then
    gcloud storage managed-folders create "$path" --project="$PROJECT"
  fi
  gcloud storage managed-folders describe "$path" --project="$PROJECT" >/dev/null
done
for role in roles/storage.objectCreator roles/storage.objectViewer; do
  gcloud storage managed-folders add-iam-policy-binding "$STAGING" --project="$PROJECT" --member="$MEMBER" --role="$role" --quiet
done
gcloud storage managed-folders add-iam-policy-binding "$LEGACY" --project="$PROJECT" --member="$MEMBER" --role=roles/storage.objectViewer --quiet
echo 'IAM setup completed; no deploy/package publication. Run separate metadata-only preflight.'

