#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-/tmp/rrgh-route-packages}"
ACCESS_TOKEN="${GOOGLE_OAUTH_ACCESS_TOKEN:-}"

if [ -z "$ACCESS_TOKEN" ]; then
  echo "GOOGLE_OAUTH_ACCESS_TOKEN is required." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR"/*.geojson

LIST_URL="https://www.googleapis.com/drive/v3/files"
LIST_JSON="$OUTPUT_DIR/shared-files.json"

curl --fail --silent --show-error   -H "Authorization: Bearer $ACCESS_TOKEN"   --get "$LIST_URL"   --data-urlencode "q=sharedWithMe = true and trashed = false"   --data-urlencode "fields=files(id,name,mimeType,size)"   --data-urlencode "pageSize=100"   -o "$LIST_JSON"

stage_route() {
  local source_name="$1"
  local package_id="$2"
  local route_id="$3"
  local expected_sha="$4"
  local expected_bytes="$5"
  local output="$OUTPUT_DIR/${package_id}.geojson"

  local count
  count="$(jq --arg name "$source_name" '[.files[] | select(.name == $name)] | length' "$LIST_JSON")"
  if [ "$count" -ne 1 ]; then
    echo "Expected exactly one governed Drive source named $source_name; found $count." >&2
    exit 1
  fi

  local file_id
  file_id="$(jq -r --arg name "$source_name" '.files[] | select(.name == $name) | .id' "$LIST_JSON")"

  curl --fail --silent --show-error     -H "Authorization: Bearer $ACCESS_TOKEN"     "https://www.googleapis.com/drive/v3/files/${file_id}?alt=media"     -o "$output"

  local actual_sha actual_bytes
  actual_sha="$(sha256sum "$output" | awk '{print $1}')"
  actual_bytes="$(stat -c '%s' "$output")"

  test "$actual_sha" = "$expected_sha" || {
    echo "Governed source SHA mismatch for $source_name." >&2
    exit 1
  }
  test "$actual_bytes" = "$expected_bytes" || {
    echo "Governed source byte-count mismatch for $source_name." >&2
    exit 1
  }

  jq -e     --arg routeID "$route_id"     '.type == "FeatureCollection"
     and (.features | type == "array")
     and any(.features[];
       .geometry.type == "LineString"
       and .properties.routeId == $routeID
       and (.geometry.coordinates | type == "array")
       and (.geometry.coordinates | length > 1)
     )'     "$output" >/dev/null

  jq -e     --arg routeID "$route_id"     'all(.features[];
      if .geometry.type == "Point" then
        (.properties.routeId == $routeID)
      else true end
    )'     "$output" >/dev/null

  echo "Staged governed route package: $package_id / $route_id / $actual_bytes bytes / $actual_sha"
}

stage_route   "skybridge-arch-v1.geojson"   "route-rte-0001"   "RTE-0001"   "123fdb57e1142299f86c714367cc466b70f18fa90cfbaabb92b0d9ced157dc66"   "8201"

stage_route   "princess-arch-v1.geojson"   "route-rte-0002"   "RTE-0002"   "ced314bb34392750b0f823c9a11bc95a48e6fa52c59830d4ee83619f615d6602"   "6533"

rm -f "$LIST_JSON"
