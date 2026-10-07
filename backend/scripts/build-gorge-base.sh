#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-/tmp/rrgh-gorge-base}"
PACKAGE_VERSION="${2:-2026.10.07.2}"
BBOX="-83.80,37.65,-83.40,37.95"
WEST="-83.80"
SOUTH="37.65"
EAST="-83.40"
NORTH="37.95"
RETRIEVED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

ROOT="$OUTPUT_DIR/root"
DOWNLOADS="$OUTPUT_DIR/downloads"
MANIFEST="$OUTPUT_DIR/gorge-base-manifest.json"
PACKAGE="$OUTPUT_DIR/gorge-base-${PACKAGE_VERSION}.rrghpkg"

rm -rf "$OUTPUT_DIR"
mkdir -p   "$ROOT/layers/terrain"   "$ROOT/layers/hydrography"   "$ROOT/layers/roads"   "$ROOT/layers/forest"   "$ROOT/layers/state"   "$ROOT/layers/osm"   "$ROOT/layers/kgs"   "$ROOT/native"   "$ROOT/native/base"   "$ROOT/native/website/data/map/weather"   "$ROOT/documentation/kgs"   "$ROOT/documentation/osm"   "$DOWNLOADS"

for command in curl jq unzip ogr2ogr ogrinfo osmium sha256sum gdal_translate tar; do
  command -v "$command" >/dev/null || {
    echo "Missing required build command: $command" >&2
    exit 1
  }
done

download() {
  local url="$1"
  local output="$2"
  curl --fail --location --retry 4 --retry-all-errors     --connect-timeout 30 --max-time 900     "$url" -o "$output"
}

arcgis_geojson() {
  local layer_url="$1"
  local output="$2"

  curl --fail --location --retry 4 --retry-all-errors     --get "$layer_url/query"     --data-urlencode "where=1=1"     --data-urlencode "geometry=$BBOX"     --data-urlencode "geometryType=esriGeometryEnvelope"     --data-urlencode "inSR=4326"     --data-urlencode "outSR=4326"     --data-urlencode "outFields=*"     --data-urlencode "returnGeometry=true"     --data-urlencode "resultRecordCount=2000"     --data-urlencode "f=geojson"     -o "$output"

  jq -e '.type == "FeatureCollection" and (.features | type == "array")'     "$output" >/dev/null
}

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

arcgis_map_export() {
  local service_url="$1"
  local output="$2"
  local format="$3"

  curl --fail --location --retry 4 --retry-all-errors \
    --connect-timeout 30 --max-time 900 \
    --get "$service_url/export" \
    --data-urlencode "bbox=$BBOX" \
    --data-urlencode "bboxSR=4326" \
    --data-urlencode "imageSR=3857" \
    --data-urlencode "size=4096,3072" \
    --data-urlencode "format=$format" \
    --data-urlencode "transparent=false" \
    --data-urlencode "f=image" \
    -o "$output"
  test -s "$output"
}

arcgis_geojson_tiled() {
  local layer_url="$1"
  local output="$2"
  local work_dir="$3"

  mkdir -p "$work_dir"

  # The national NHDPlus_HR dynamic service can stall on denser Gorge
  # quadrants even when the overall AOI is small. Query a deterministic 4x4
  # grid and request geometry plus OBJECTID only; native rendering does not
  # consume the remaining NHD attributes.
  local lon_edges=(
    "-83.80" "-83.70" "-83.60" "-83.50" "-83.40"
  )
  local lat_edges=(
    "37.65" "37.725" "37.80" "37.875" "37.95"
  )

  local parts=()
  local index=0
  local row col
  for row in 0 1 2 3; do
    for col in 0 1 2 3; do
      local bbox="${lon_edges[$col]},${lat_edges[$row]},${lon_edges[$((col + 1))]},${lat_edges[$((row + 1))]}"
      local part="$work_dir/part-$index.geojson"

      echo "USGS NHDPlus_HR tile $index bbox=$bbox"
      curl --fail --location --retry 4 --retry-all-errors \
        --retry-delay 2 --retry-max-time 300 \
        --connect-timeout 20 --max-time 60 \
        --get "$layer_url/query" \
        --data-urlencode "where=1=1" \
        --data-urlencode "geometry=$bbox" \
        --data-urlencode "geometryType=esriGeometryEnvelope" \
        --data-urlencode "inSR=4326" \
        --data-urlencode "outSR=4326" \
        --data-urlencode "spatialRel=esriSpatialRelIntersects" \
        --data-urlencode "outFields=OBJECTID" \
        --data-urlencode "returnGeometry=true" \
        --data-urlencode "returnZ=false" \
        --data-urlencode "returnM=false" \
        --data-urlencode "geometryPrecision=5" \
        --data-urlencode "resultRecordCount=2000" \
        --data-urlencode "f=geojson" \
        -o "$part"

      jq -e '
        .type == "FeatureCollection"
        and (.features | type == "array")
        and (.exceededTransferLimit // false | not)
      ' "$part" >/dev/null

      parts+=("$part")
      index=$((index + 1))
    done
  done

  jq -s '
    {
      type:"FeatureCollection",
      features:
        (
          [.[].features[]]
          | unique_by(
              .properties.OBJECTID
              // .properties.objectid
              // (.geometry | tostring)
            )
        )
    }
  ' "${parts[@]}" > "$output"

  jq -e '
    .type == "FeatureCollection"
    and (.features | type == "array")
  ' "$output" >/dev/null
}

# 1. Terrain / hillshade — exact KyFromAbove ImageServer export, bounded to RRGH AOI.
KYFROMABOVE_SERVICE="https://kyraster.ky.gov/arcgis/rest/services/ElevationServices/Ky_DEM_KYAPED_2FT_Phase3_MultiDirectionalHillshade_WGS84WM/ImageServer"
KYFROMABOVE_OUT="$ROOT/layers/terrain/kyfromabove-hillshade.tif"
curl --fail --location --retry 4 --retry-all-errors   --get "$KYFROMABOVE_SERVICE/exportImage"   --data-urlencode "bbox=$BBOX"   --data-urlencode "bboxSR=4326"   --data-urlencode "imageSR=3857"   --data-urlencode "size=4096,3072"   --data-urlencode "format=tiff"   --data-urlencode "interpolation=RSP_BilinearInterpolation"   --data-urlencode "f=image"   -o "$KYFROMABOVE_OUT"
test -s "$KYFROMABOVE_OUT"

# Native offline renderer derivative. This is built from the exact governed
# hillshade export above so the app can render terrain without requiring
# MapKit/third-party network tiles in the field.
NATIVE_HILLSHADE="$ROOT/native/base/terrain-relief.png"
gdal_translate -q -of PNG "$KYFROMABOVE_OUT" "$NATIVE_HILLSHADE"
test -s "$NATIVE_HILLSHADE"

# Offline raster counterparts for the accepted Website map views. These are
# single bounded exports of the supported Gorge AOI — never bulk tile scraping.
KY_TOPO_SERVICE="https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_KyTopo_Map_Series_WGS84WM/MapServer"
USGS_TOPO_SERVICE="https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer"
LEAF_ON_SERVICE="https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase3_3IN_WGS84WM/MapServer"
LEAF_OFF_SERVICE="https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Imagery_Phase2_6IN_WGS84WM/MapServer"

NATIVE_KY_TOPO="$ROOT/native/base/kentucky-topo.png"
NATIVE_USGS_TOPO="$ROOT/native/base/usgs-topo.png"
NATIVE_LEAF_ON="$ROOT/native/base/leaf-on-aerial.jpg"
NATIVE_LEAF_OFF="$ROOT/native/base/leaf-off-aerial.jpg"

arcgis_map_export "$KY_TOPO_SERVICE" "$NATIVE_KY_TOPO" "png32"
arcgis_map_export "$USGS_TOPO_SERVICE" "$NATIVE_USGS_TOPO" "png32"
arcgis_map_export "$LEAF_ON_SERVICE" "$NATIVE_LEAF_ON" "jpg"
arcgis_map_export "$LEAF_OFF_SERVICE" "$NATIVE_LEAF_OFF" "jpg"

# 2. USGS NHDPlus High Resolution — fixed downloadable HU4 snapshot.
# The nationwide dynamic ArcGIS service repeatedly returned 502/504/timeouts
# even for small deterministic subqueries in CI. USGS explicitly publishes
# NHDPlus HR as staged downloadable HU4 products; Red River Gorge is within
# HU4 0510 (Kentucky-Licking). Use the official staged GDB product and clip
# locally so package generation does not depend on expensive live rendering.
USGS_NHD_PRODUCT="https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Hydrography/NHDPlus/HU4/HighResolution/GDB/NHDPLUS_H_0510_HU4_GDB.zip"
USGS_NHD_ZIP="$DOWNLOADS/NHDPLUS_H_0510_HU4_GDB.zip"
USGS_NHD_DIR="$DOWNLOADS/nhdplus-0510"
download "$USGS_NHD_PRODUCT" "$USGS_NHD_ZIP"
mkdir -p "$USGS_NHD_DIR"
unzip -q "$USGS_NHD_ZIP" -d "$USGS_NHD_DIR"
USGS_NHD_GDB="$(find "$USGS_NHD_DIR" -type d -name '*.gdb' | head -n 1)"
test -n "$USGS_NHD_GDB"

ogr2ogr -f GeoJSON \
  -t_srs EPSG:4326 \
  -spat "$WEST" "$SOUTH" "$EAST" "$NORTH" \
  -spat_srs EPSG:4326 \
  "$ROOT/layers/hydrography/usgs-nhd-flowline.geojson" \
  "$USGS_NHD_GDB" \
  NHDFlowline

ogr2ogr -f GeoJSON \
  -t_srs EPSG:4326 \
  -spat "$WEST" "$SOUTH" "$EAST" "$NORTH" \
  -spat_srs EPSG:4326 \
  "$ROOT/layers/hydrography/usgs-nhd-waterbody.geojson" \
  "$USGS_NHD_GDB" \
  NHDWaterbody

jq -e '.type == "FeatureCollection" and (.features | type == "array") and (.features | length > 0)' \
  "$ROOT/layers/hydrography/usgs-nhd-flowline.geojson" >/dev/null
jq -e '.type == "FeatureCollection" and (.features | type == "array")' \
  "$ROOT/layers/hydrography/usgs-nhd-waterbody.geojson" >/dev/null

# 3. 2025 Census TIGER/Line county Roads — latest published county Roads snapshot for Powell, Wolfe, Menifee, Lee.
CENSUS_BASE="https://www2.census.gov/geo/tiger/TIGER2025/ROADS"
: > "$DOWNLOADS/census-features.ndjson"
for fips in 21129 21165 21197 21237; do
  ZIP="$DOWNLOADS/tl_2025_${fips}_roads.zip"
  DIR="$DOWNLOADS/census-${fips}"
  download "$CENSUS_BASE/tl_2025_${fips}_roads.zip" "$ZIP"
  mkdir -p "$DIR"
  unzip -q "$ZIP" -d "$DIR"
  SHP="$(find "$DIR" -type f -name '*.shp' | head -n 1)"
  test -n "$SHP"
  TMP="$DIR/clipped.geojson"
  ogr2ogr -f GeoJSON     -t_srs EPSG:4326     -spat "$WEST" "$SOUTH" "$EAST" "$NORTH"     -spat_srs EPSG:4326     "$TMP" "$SHP"
  jq -c '.features[]' "$TMP" >> "$DOWNLOADS/census-features.ndjson"
done
jq -s '{type:"FeatureCollection",features:.}'   "$DOWNLOADS/census-features.ndjson"   > "$ROOT/layers/roads/census-tiger-roads.geojson"

# 4. USDA Forest Service bounded snapshots.
USFS_TRAILS="https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_TrailNFSPublishWithDataStatus_01/MapServer/0"
USFS_ROADS="https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_RoadBasic_01/MapServer/0"
USFS_OWNERSHIP="https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_BasicOwnership_01/MapServer/0"

arcgis_geojson "$USFS_TRAILS" "$ROOT/layers/forest/usfs-nfs-trails.geojson"
arcgis_geojson "$USFS_ROADS" "$ROOT/layers/forest/usfs-nfs-roads.geojson"
arcgis_geojson "$USFS_OWNERSHIP" "$ROOT/layers/forest/usfs-basic-ownership.geojson"

# Static Website-parity context layers that are legally cleared for the Base
# package. These remain informational and do not establish access or boundaries.
STATE_PARK_TRAILS="https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_State_Parks_Features_WGS84WM/MapServer/9"
USFS_WILDERNESS="https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_Wilderness_01/MapServer/0"
USFS_SPECIAL="https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_SpecialInterestManagementArea_01/MapServer/0"
USFS_LAND_UNITS="https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_NFSLandUnit_01/MapServer/0"
KY_COUNTIES="https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_CountyLines_WGS84WM/MapServer/0"

arcgis_geojson "$STATE_PARK_TRAILS" "$ROOT/layers/state/ky-state-park-trails.geojson"
arcgis_geojson "$USFS_WILDERNESS" "$ROOT/layers/forest/usfs-wilderness.geojson"
arcgis_geojson "$USFS_SPECIAL" "$ROOT/layers/forest/usfs-special-management.geojson"
arcgis_geojson "$USFS_LAND_UNITS" "$ROOT/layers/forest/usfs-land-units.geojson"
arcgis_geojson "$KY_COUNTIES" "$ROOT/layers/state/ky-counties.geojson"

# 5. OpenStreetMap — fixed Geofabrik Kentucky snapshot, clipped and transformed locally.
OSM_URL="https://download.geofabrik.de/north-america/us/kentucky-260901.osm.pbf"
OSM_SOURCE="$DOWNLOADS/kentucky-260901.osm.pbf"
OSM_CLIP="$DOWNLOADS/gorge.osm.pbf"
OSM_FILTERED="$DOWNLOADS/gorge-highways.osm.pbf"
download "$OSM_URL" "$OSM_SOURCE"
osmium extract --overwrite -b "$BBOX" "$OSM_SOURCE" -o "$OSM_CLIP"
osmium tags-filter --overwrite "$OSM_CLIP" w/highway r/route=hiking -o "$OSM_FILTERED"
osmium export --overwrite "$OSM_FILTERED"   -o "$ROOT/layers/osm/osm-community-local-context.geojson"

cat > "$ROOT/documentation/osm/ODBL-NOTICE.txt" <<'EOF'
This offline component contains information derived from OpenStreetMap data.
© OpenStreetMap contributors. OpenStreetMap data is available under the
Open Database License (ODbL) 1.0: https://www.openstreetmap.org/copyright
Source snapshot: Geofabrik Kentucky extract. RRGH clips and transforms the
database for the Red River Gorge supported area. This notice applies to the
OSM-derived database component; it does not license proprietary RRGH route
geometry or other separately licensed/public-domain package components.
EOF

# 6. Kentucky Geological Survey Oil & Gas Well Location dataset.
KGS_URL="https://kgs.uky.edu/ogdata/kyog_dd.zip"
KGS_INFO_URL="https://kgs.uky.edu/ogdata/kyog_info.txt"
KGS_ZIP="$DOWNLOADS/kyog_dd.zip"
KGS_DIR="$DOWNLOADS/kgs"
download "$KGS_URL" "$KGS_ZIP"
download "$KGS_INFO_URL" "$ROOT/documentation/kgs/kyog_info.txt"
mkdir -p "$KGS_DIR"
unzip -q "$KGS_ZIP" -d "$KGS_DIR"
KGS_SHP="$(find "$KGS_DIR" -type f -name '*.shp' | head -n 1)"
test -n "$KGS_SHP"
ogr2ogr -f GeoJSON   -t_srs EPSG:4326   -spat "$WEST" "$SOUTH" "$EAST" "$NORTH"   -spat_srs EPSG:4326   "$ROOT/layers/kgs/kgs-oil-gas-wells.geojson"   "$KGS_SHP"

cat > "$ROOT/documentation/kgs/RRGH-MODIFICATION-NOTICE.txt" <<EOF
Red River Gorge Hiker package version $PACKAGE_VERSION contains a geographic
clip/format conversion of the Kentucky Geological Survey Oil and Gas Well
Location dataset for the RRGH supported-area AOI ($BBOX). The included
kyog_info.txt is the provider documentation retrieved with this package build.
KGS/University of Kentucky source attribution and provider disclaimer remain
applicable. This derivative is not represented as a live or authoritative
well-status service.
EOF

# 7. Accepted RRGH Website map derivatives — frozen exact staging source.
# The nonproduction package consumes only RRGH-controlled derivative artifacts
# from the exact accepted Website map source commit. Production packaging must
# point at a promoted production source before release.
RRGH_MAP_SOURCE_SHA="2e8dd27db788f1a93017fe8146c5c28e40734a68"
RRGH_RAW_BASE="https://raw.githubusercontent.com/ryanredrivergorgehiker/red-river-gorge-hiker/$RRGH_MAP_SOURCE_SHA/public"
RRGH_WEBSITE_ROOT="$ROOT/native/website"
SUN_MANIFEST_REL="data/map/rrg-lidar-sun-mobile-manifest.json"
WEATHER_MANIFEST_REL="data/map/weather/manifest.json"

mkdir -p "$RRGH_WEBSITE_ROOT/data/map/rrg-lidar-sun-mobile" "$RRGH_WEBSITE_ROOT/data/map/weather"
download "$RRGH_RAW_BASE/$SUN_MANIFEST_REL" "$RRGH_WEBSITE_ROOT/$SUN_MANIFEST_REL"
download "$RRGH_RAW_BASE/$WEATHER_MANIFEST_REL" "$RRGH_WEBSITE_ROOT/$WEATHER_MANIFEST_REL"

while IFS= read -r rel; do
  test -n "$rel" || continue
  mkdir -p "$RRGH_WEBSITE_ROOT/$(dirname "$rel")"
  download "$RRGH_RAW_BASE/$rel" "$RRGH_WEBSITE_ROOT/$rel"
done < <(
  jq -r '
    .sectors[]
    | .variants.overview.sunrise.file,
      .variants.overview.sunset.file,
      .variants.detail.sunrise.file,
      .variants.detail.sunset.file
  ' "$RRGH_WEBSITE_ROOT/$SUN_MANIFEST_REL" | sort -u
)

while IFS= read -r rel; do
  test -n "$rel" || continue
  mkdir -p "$RRGH_WEBSITE_ROOT/$(dirname "$rel")"
  download "$RRGH_RAW_BASE/$rel" "$RRGH_WEBSITE_ROOT/$rel"
done < <(
  jq -r '.products[].file' "$RRGH_WEBSITE_ROOT/$WEATHER_MANIFEST_REL" | sort -u
)

# Freeze a complete hash index for every native Website derivative so the
# client can validate each member before accepting it for offline rendering.
STATIC_ASSETS_NDJSON="$DOWNLOADS/native-static-assets.ndjson"
STATIC_ASSETS_JSON="$DOWNLOADS/native-static-assets.json"
: > "$STATIC_ASSETS_NDJSON"
while IFS= read -r path; do
  rel="${path#$ROOT/}"
  sha="$(hash_file "$path")"
  jq -nc --arg path "$rel" --arg sha "$sha"     '{path:$path,sha256:$sha}' >> "$STATIC_ASSETS_NDJSON"
done < <(find "$RRGH_WEBSITE_ROOT" -type f | sort)
jq -s '.' "$STATIC_ASSETS_NDJSON" > "$STATIC_ASSETS_JSON"

# Freeze per-output source integrity before creating the package archive.
KY_SHA="$(hash_file "$KYFROMABOVE_OUT")"
NHD_FLOW_SHA="$(hash_file "$ROOT/layers/hydrography/usgs-nhd-flowline.geojson")"
NHD_WATER_SHA="$(hash_file "$ROOT/layers/hydrography/usgs-nhd-waterbody.geojson")"
NHD_SOURCE_SHA="$(hash_file "$USGS_NHD_ZIP")"
CENSUS_SHA="$(hash_file "$ROOT/layers/roads/census-tiger-roads.geojson")"
USFS_TRAILS_SHA="$(hash_file "$ROOT/layers/forest/usfs-nfs-trails.geojson")"
USFS_ROADS_SHA="$(hash_file "$ROOT/layers/forest/usfs-nfs-roads.geojson")"
USFS_OWNER_SHA="$(hash_file "$ROOT/layers/forest/usfs-basic-ownership.geojson")"
OSM_SHA="$(hash_file "$ROOT/layers/osm/osm-community-local-context.geojson")"
KGS_SHA="$(hash_file "$ROOT/layers/kgs/kgs-oil-gas-wells.geojson")"
NATIVE_HILLSHADE_SHA="$(hash_file "$NATIVE_HILLSHADE")"
NATIVE_KY_TOPO_SHA="$(hash_file "$NATIVE_KY_TOPO")"
NATIVE_USGS_TOPO_SHA="$(hash_file "$NATIVE_USGS_TOPO")"
NATIVE_LEAF_ON_SHA="$(hash_file "$NATIVE_LEAF_ON")"
NATIVE_LEAF_OFF_SHA="$(hash_file "$NATIVE_LEAF_OFF")"
STATE_PARK_TRAILS_SHA="$(hash_file "$ROOT/layers/state/ky-state-park-trails.geojson")"
USFS_WILDERNESS_SHA="$(hash_file "$ROOT/layers/forest/usfs-wilderness.geojson")"
USFS_SPECIAL_SHA="$(hash_file "$ROOT/layers/forest/usfs-special-management.geojson")"
USFS_LAND_UNITS_SHA="$(hash_file "$ROOT/layers/forest/usfs-land-units.geojson")"
KY_COUNTIES_SHA="$(hash_file "$ROOT/layers/state/ky-counties.geojson")"
SUN_MANIFEST_SHA="$(hash_file "$RRGH_WEBSITE_ROOT/$SUN_MANIFEST_REL")"
WEATHER_MANIFEST_SHA="$(hash_file "$RRGH_WEBSITE_ROOT/$WEATHER_MANIFEST_REL")"
OSM_SOURCE_SHA="$(hash_file "$OSM_SOURCE")"
KGS_SOURCE_SHA="$(hash_file "$KGS_ZIP")"

cat > "$ROOT/NATIVE-MAP.json" <<EOF
{
  "schemaVersion": 1,
  "archiveFormat": "tar",
  "packageID": "gorge-base",
  "packageVersion": "$PACKAGE_VERSION",
  "boundsWgs84": {
    "west": $WEST,
    "south": $SOUTH,
    "east": $EAST,
    "north": $NORTH
  },
  "terrainRelief": {
    "path": "native/base/terrain-relief.png",
    "sha256": "$NATIVE_HILLSHADE_SHA"
  },
  "baseRasters": [
    {"id":"kentucky-topo","path":"native/base/kentucky-topo.png","sha256":"$NATIVE_KY_TOPO_SHA"},
    {"id":"usgs-topo","path":"native/base/usgs-topo.png","sha256":"$NATIVE_USGS_TOPO_SHA"},
    {"id":"terrain-relief","path":"native/base/terrain-relief.png","sha256":"$NATIVE_HILLSHADE_SHA"},
    {"id":"leaf-on-aerial","path":"native/base/leaf-on-aerial.jpg","sha256":"$NATIVE_LEAF_ON_SHA"},
    {"id":"leaf-off-aerial","path":"native/base/leaf-off-aerial.jpg","sha256":"$NATIVE_LEAF_OFF_SHA"}
  ],
  "vectors": [
    {"id":"hydro-flowline","path":"layers/hydrography/usgs-nhd-flowline.geojson","sha256":"$NHD_FLOW_SHA"},
    {"id":"hydro-waterbody","path":"layers/hydrography/usgs-nhd-waterbody.geojson","sha256":"$NHD_WATER_SHA"},
    {"id":"local-roads","path":"layers/roads/census-tiger-roads.geojson","sha256":"$CENSUS_SHA"},
    {"id":"forest-service-trails","path":"layers/forest/usfs-nfs-trails.geojson","sha256":"$USFS_TRAILS_SHA"},
    {"id":"state-park-trails","path":"layers/state/ky-state-park-trails.geojson","sha256":"$STATE_PARK_TRAILS_SHA"},
    {"id":"forest-service-roads","path":"layers/forest/usfs-nfs-roads.geojson","sha256":"$USFS_ROADS_SHA"},
    {"id":"forest-ownership","path":"layers/forest/usfs-basic-ownership.geojson","sha256":"$USFS_OWNER_SHA"},
    {"id":"wilderness","path":"layers/forest/usfs-wilderness.geojson","sha256":"$USFS_WILDERNESS_SHA"},
    {"id":"special-management","path":"layers/forest/usfs-special-management.geojson","sha256":"$USFS_SPECIAL_SHA"},
    {"id":"national-forest-land","path":"layers/forest/usfs-land-units.geojson","sha256":"$USFS_LAND_UNITS_SHA"},
    {"id":"county-boundaries","path":"layers/state/ky-counties.geojson","sha256":"$KY_COUNTIES_SHA"},
    {"id":"community-informal","path":"layers/osm/osm-community-local-context.geojson","sha256":"$OSM_SHA"},
    {"id":"oil-gas-wells","path":"layers/kgs/kgs-oil-gas-wells.geojson","sha256":"$KGS_SHA"}
  ],
  "websiteAssetsRoot": "native/website",
  "sunPotentialManifest": {
    "path": "native/website/$SUN_MANIFEST_REL",
    "sha256": "$SUN_MANIFEST_SHA",
    "sourceCommit": "$RRGH_MAP_SOURCE_SHA"
  },
  "weatherManifest": {
    "path": "native/website/$WEATHER_MANIFEST_REL",
    "sha256": "$WEATHER_MANIFEST_SHA",
    "sourceCommit": "$RRGH_MAP_SOURCE_SHA"
  },
  "staticAssets": $(cat "$STATIC_ASSETS_JSON")
}
EOF
jq -n   --arg packageVersion "$PACKAGE_VERSION"   --arg builtAt "$RETRIEVED_AT"   --arg bbox "$BBOX"   --arg osmSourceSha "$OSM_SOURCE_SHA"   --arg kgsSourceSha "$KGS_SOURCE_SHA"   --arg rrghMapSha "$RRGH_MAP_SOURCE_SHA"    '{
    packageID:"gorge-base",
    packageVersion:$packageVersion,
    builtAt:$builtAt,
    areaOfInterest:{bboxWgs84:$bbox,note:"RRGH supported-area build AOI; not a legal boundary"},
    sourceArchiveIntegrity:{
      geofabrikKentuckyPbfSHA256:$osmSourceSha,
      kgsOilGasZipSHA256:$kgsSourceSha
    },
    exclusions:{
      protectedRouteGeometry:"Delivered as separately entitlement-authorized route packages; not embedded in Gorge Base.",
      streamStats:"Paid connected-only under LEG-DEC-0033; no offline substitute.",
      parcels:"Excluded pending exact authorized source.",
      gaiaCalTopoPublicTiles:"Excluded; no proprietary/public tile scraping.",
      scheduledWeather:"Latest accepted RRGH-hosted NOAA/NWS snapshot is embedded with its fetchedAtUtc timestamp for truthful last-known offline display; a later refresh package/workflow may supersede it independently.",
      websiteParitySource:("Exact RRGH Website map derivative source commit " + $rrghMapSha),
      archiveFormat:"Plain deterministic tar so the native app can safely extract verified package members without a third-party decompression dependency."
    }
  }' > "$ROOT/BUILD-PROVENANCE.json"

# Deterministic archive framing for these exact built files.
# Version 2026.10.07.2 extends Gorge Base to a plain tar container. The package
# remains immutable and SHA-256 verified before install; the native client can
# now extract governed components using a small fail-closed tar reader rather
# than treating the offline package as an opaque blob.
(
  cd "$ROOT"
  tar --sort=name     --mtime='UTC 2026-10-07 00:00:00'     --owner=0 --group=0 --numeric-owner     -cf "$PACKAGE" .
)

PACKAGE_SHA="$(hash_file "$PACKAGE")"
PACKAGE_BYTES="$(stat -c '%s' "$PACKAGE")"

# External manifest shape is exactly the Lane 21 OfflinePackageManifest contract.
jq -n   --arg packageID "gorge-base"   --arg version "$PACKAGE_VERSION"   --argjson byteCount "$PACKAGE_BYTES"   --arg sha256 "$PACKAGE_SHA"   --arg retrievedAt "$RETRIEVED_AT"   --arg bbox "$BBOX"   --arg kyUrl "$KYFROMABOVE_SERVICE"   --arg kySha "$KY_SHA"   --arg nhdUrl "$USGS_NHD_PRODUCT"   --arg nhdSourceSha "$NHD_SOURCE_SHA"   --arg nhdFlowSha "$NHD_FLOW_SHA"   --arg nhdWaterSha "$NHD_WATER_SHA"   --arg censusUrl "$CENSUS_BASE"   --arg censusSha "$CENSUS_SHA"   --arg usfsTrails "$USFS_TRAILS"   --arg usfsTrailsSha "$USFS_TRAILS_SHA"   --arg usfsRoads "$USFS_ROADS"   --arg usfsRoadsSha "$USFS_ROADS_SHA"   --arg usfsOwnership "$USFS_OWNERSHIP"   --arg usfsOwnershipSha "$USFS_OWNER_SHA"   --arg kyTopo "$KY_TOPO_SERVICE"   --arg kyTopoSha "$NATIVE_KY_TOPO_SHA"   --arg usgsTopo "$USGS_TOPO_SERVICE"   --arg usgsTopoSha "$NATIVE_USGS_TOPO_SHA"   --arg leafOn "$LEAF_ON_SERVICE"   --arg leafOnSha "$NATIVE_LEAF_ON_SHA"   --arg leafOff "$LEAF_OFF_SERVICE"   --arg leafOffSha "$NATIVE_LEAF_OFF_SHA"   --arg stateParkTrails "$STATE_PARK_TRAILS"   --arg stateParkTrailsSha "$STATE_PARK_TRAILS_SHA"   --arg usfsWilderness "$USFS_WILDERNESS"   --arg usfsWildernessSha "$USFS_WILDERNESS_SHA"   --arg usfsSpecial "$USFS_SPECIAL"   --arg usfsSpecialSha "$USFS_SPECIAL_SHA"   --arg usfsLandUnits "$USFS_LAND_UNITS"   --arg usfsLandUnitsSha "$USFS_LAND_UNITS_SHA"   --arg kyCounties "$KY_COUNTIES"   --arg kyCountiesSha "$KY_COUNTIES_SHA"   --arg rrghMapSha "$RRGH_MAP_SOURCE_SHA"   --arg sunManifestSha "$SUN_MANIFEST_SHA"   --arg weatherManifestSha "$WEATHER_MANIFEST_SHA"   --arg osmUrl "$OSM_URL"   --arg osmSha "$OSM_SHA"   --arg kgsUrl "$KGS_URL"   --arg kgsSha "$KGS_SHA"   '{
    packageID:$packageID,
    version:$version,
    byteCount:$byteCount,
    sha256:$sha256,
    sources:[
      {
        sourceID:"kyfromabove-hillshade",
        sourceURL:$kyUrl,
        provider:"Commonwealth of Kentucky / KyFromAbove",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("WGS84 bbox " + $bbox + "; Phase 3 2-ft DEM multidirectional hillshade ImageServer export"),
        processingMethod:"Single bounded ImageServer exportImage request to GeoTIFF; no cached tile scraping; packaged as terrain context.",
        rightsBasis:"LEG-DEC-0033 / LEG-REF-0021 public-domain Kentucky source-data basis.",
        attributionOrDisclaimer:"Kentucky From Above / Commonwealth of Kentucky; terrain context is informational and not a legal boundary or access determination.",
        outputVersion:$version,
        integritySHA256:$kySha
      },
      {
        sourceID:"usgs-nhdplus-flowline",
        sourceURL:$nhdUrl,
        sourceArchiveSHA256:$nhdSourceSha,
        provider:"U.S. Geological Survey / The National Map",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Official staged NHDPlus HR HU4 0510 GDB product, NHDFlowline clipped locally to WGS84 bbox " + $bbox),
        processingMethod:"Downloaded the official staged HU4 0510 file geodatabase; ogr2ogr clipped/reprojected NHDFlowline locally to GeoJSON. Exact source archive and output hashes are frozen.",
        rightsBasis:"U.S. federal public-domain geospatial data; LEG-DEC-0033 / LEG-REF-0025.",
        attributionOrDisclaimer:"USGS / The National Map; fixed contextual hydrography snapshot, not live regulatory or access data.",
        outputVersion:$version,
        integritySHA256:$nhdFlowSha
      },
      {
        sourceID:"usgs-nhdplus-waterbody",
        sourceURL:$nhdUrl,
        sourceArchiveSHA256:$nhdSourceSha,
        provider:"U.S. Geological Survey / The National Map",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Official staged NHDPlus HR HU4 0510 GDB product, NHDWaterbody clipped locally to WGS84 bbox " + $bbox),
        processingMethod:"Downloaded the official staged HU4 0510 file geodatabase; ogr2ogr clipped/reprojected NHDWaterbody locally to GeoJSON. Exact source archive and output hashes are frozen.",
        rightsBasis:"U.S. federal public-domain geospatial data; LEG-DEC-0033 / LEG-REF-0025.",
        attributionOrDisclaimer:"USGS / The National Map; fixed contextual hydrography snapshot, not live regulatory or access data.",
        outputVersion:$version,
        integritySHA256:$nhdWaterSha
      },
      {
        sourceID:"census-tiger-roads",
        sourceURL:$censusUrl,
        provider:"U.S. Census Bureau",
        vintageOrRetrievedAt:"2025 TIGER/Line Roads",
        areaOfInterestOrSourceObjects:("Lee 21129, Menifee 21165, Powell 21197, Wolfe 21237 county Roads from the latest published 2025 TIGER/Line Roads release, clipped to WGS84 bbox " + $bbox),
        processingMethod:"Downloaded official 2025 county Roads shapefiles; ogr2ogr bounded clip/reprojection; merged as one GeoJSON FeatureCollection.",
        rightsBasis:"U.S. Census Bureau public-use federal geographic data; LEG-DEC-0033 / LEG-REF-0040.",
        attributionOrDisclaimer:"U.S. Census Bureau TIGER/Line; road context is informational and does not establish current access, drivability, closure status, title or legal boundary.",
        outputVersion:$version,
        integritySHA256:$censusSha
      },
      {
        sourceID:"usfs-nfs-trails",
        sourceURL:$usfsTrails,
        provider:"USDA Forest Service Enterprise Data Warehouse",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("National Forest System Trails layer 0 query within WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS feature-layer GeoJSON query; no basemap/tile scraping.",
        rightsBasis:"USDA Forest Service public geospatial service; LEG-DEC-0033 / LEG-REF-0025.",
        attributionOrDisclaimer:"USDA Forest Service. Data are informational, dynamic, not legal documents, and must not be used to determine title, ownership, legal boundaries, access or current conditions.",
        outputVersion:$version,
        integritySHA256:$usfsTrailsSha
      },
      {
        sourceID:"usfs-nfs-roads",
        sourceURL:$usfsRoads,
        provider:"USDA Forest Service Enterprise Data Warehouse",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("NFS Road Basic layer query within WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS feature-layer GeoJSON query; no basemap/tile scraping.",
        rightsBasis:"USDA Forest Service public geospatial service; LEG-DEC-0033 / LEG-REF-0025.",
        attributionOrDisclaimer:"USDA Forest Service. Roads are informational and do not establish current drivability, closures, legal access, title or boundaries.",
        outputVersion:$version,
        integritySHA256:$usfsRoadsSha
      },
      {
        sourceID:"usfs-basic-ownership",
        sourceURL:$usfsOwnership,
        provider:"USDA Forest Service Enterprise Data Warehouse",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Basic Ownership layer query within WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS feature-layer GeoJSON query; no basemap/tile scraping.",
        rightsBasis:"USDA Forest Service public geospatial service; LEG-DEC-0033 / LEG-REF-0025.",
        attributionOrDisclaimer:"USDA Forest Service. Ownership/boundary context is informational and is not a survey, title opinion, legal description or access determination.",
        outputVersion:$version,
        integritySHA256:$usfsOwnershipSha
      },
      {
        sourceID:"kentucky-topo-offline",
        sourceURL:$kyTopo,
        provider:"Commonwealth of Kentucky / Kentucky Division of Geographic Information",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Kentucky Topo bounded Web Mercator export for WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS MapServer export request to PNG; no bulk tile scraping.",
        rightsBasis:"LEG-DEC-0033 approved Kentucky source stack.",
        attributionOrDisclaimer:"KyFromAbove Partners / Kentucky Division of Geographic Information.",
        outputVersion:$version,
        integritySHA256:$kyTopoSha
      },
      {
        sourceID:"usgs-topo-offline",
        sourceURL:$usgsTopo,
        provider:"U.S. Geological Survey / The National Map",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("USGS Topo bounded Web Mercator export for WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS MapServer export request to PNG; no bulk tile scraping.",
        rightsBasis:"U.S. federal public-domain geospatial data; LEG-DEC-0033.",
        attributionOrDisclaimer:"USGS The National Map.",
        outputVersion:$version,
        integritySHA256:$usgsTopoSha
      },
      {
        sourceID:"kyfromabove-leaf-on-aerial-offline",
        sourceURL:$leafOn,
        provider:"Commonwealth of Kentucky / KyFromAbove",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Phase 3 leaf-on aerial bounded Web Mercator export for WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS MapServer export request to JPEG; no bulk tile scraping.",
        rightsBasis:"LEG-DEC-0033 approved Kentucky source stack.",
        attributionOrDisclaimer:"KyFromAbove / Commonwealth of Kentucky.",
        outputVersion:$version,
        integritySHA256:$leafOnSha
      },
      {
        sourceID:"kyfromabove-leaf-off-aerial-offline",
        sourceURL:$leafOff,
        provider:"Commonwealth of Kentucky / KyFromAbove",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Phase 2 leaf-off aerial bounded Web Mercator export for WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS MapServer export request to JPEG; no bulk tile scraping.",
        rightsBasis:"LEG-DEC-0033 approved Kentucky source stack.",
        attributionOrDisclaimer:"KyFromAbove / Commonwealth of Kentucky.",
        outputVersion:$version,
        integritySHA256:$leafOffSha
      },
      {
        sourceID:"kentucky-state-park-trails",
        sourceURL:$stateParkTrails,
        provider:"Kentucky State Parks / Kentucky Division of Geographic Information",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Official State Park Trails layer clipped to WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS feature-layer GeoJSON query.",
        rightsBasis:"LEG-DEC-0033 approved Kentucky public-source stack.",
        attributionOrDisclaimer:"Kentucky State Parks / Kentucky Division of Geographic Information; trail display is informational.",
        outputVersion:$version,
        integritySHA256:$stateParkTrailsSha
      },
      {
        sourceID:"usfs-wilderness",
        sourceURL:$usfsWilderness,
        provider:"USDA Forest Service Enterprise Data Warehouse",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Wilderness layer clipped to WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS feature-layer GeoJSON query.",
        rightsBasis:"USDA Forest Service public geospatial service; LEG-DEC-0033.",
        attributionOrDisclaimer:"USDA Forest Service; informational management context, not a survey or access determination.",
        outputVersion:$version,
        integritySHA256:$usfsWildernessSha
      },
      {
        sourceID:"usfs-special-management",
        sourceURL:$usfsSpecial,
        provider:"USDA Forest Service Enterprise Data Warehouse",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Special-interest management-area layer clipped to WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS feature-layer GeoJSON query.",
        rightsBasis:"USDA Forest Service public geospatial service; LEG-DEC-0033.",
        attributionOrDisclaimer:"USDA Forest Service; informational management context, not a survey or access determination.",
        outputVersion:$version,
        integritySHA256:$usfsSpecialSha
      },
      {
        sourceID:"usfs-land-units",
        sourceURL:$usfsLandUnits,
        provider:"USDA Forest Service Enterprise Data Warehouse",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("National Forest System land-unit layer clipped to WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS feature-layer GeoJSON query.",
        rightsBasis:"USDA Forest Service public geospatial service; LEG-DEC-0033.",
        attributionOrDisclaimer:"USDA Forest Service; informational land-management context, not a legal boundary.",
        outputVersion:$version,
        integritySHA256:$usfsLandUnitsSha
      },
      {
        sourceID:"kentucky-county-boundaries",
        sourceURL:$kyCounties,
        provider:"Kentucky Division of Geographic Information",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("County boundary layer clipped to WGS84 bbox " + $bbox),
        processingMethod:"Single bounded ArcGIS feature-layer GeoJSON query.",
        rightsBasis:"LEG-DEC-0033 approved Kentucky public-source stack.",
        attributionOrDisclaimer:"Kentucky Division of Geographic Information; contextual county boundaries are not survey products.",
        outputVersion:$version,
        integritySHA256:$kyCountiesSha
      },
      {
        sourceID:"rrgh-terrain-sun-potential",
        sourceURL:("https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/commit/" + $rrghMapSha),
        provider:"Red River Gorge Hiker",
        vintageOrRetrievedAt:$rrghMapSha,
        areaOfInterestOrSourceObjects:"Accepted RRGH 30-sector mobile Sunrise / Sunset Potential derivative manifest and raster set.",
        processingMethod:"Copied exact RRGH-controlled accepted Website derivative bytes from the frozen source commit into the protected Base package; every packaged file is SHA-256 indexed by NATIVE-MAP.json.",
        rightsBasis:"RRGH-controlled derivative of LEG-DEC-0033 cleared terrain/source stack.",
        attributionOrDisclaimer:"RRGH terrain-derived potential model; bare-earth/source limitations remain visible in the app.",
        outputVersion:$version,
        integritySHA256:$sunManifestSha
      },
      {
        sourceID:"rrgh-noaa-weather-snapshot",
        sourceURL:("https://github.com/ryanredrivergorgehiker/red-river-gorge-hiker/commit/" + $rrghMapSha),
        provider:"Red River Gorge Hiker derivative from NOAA / National Weather Service",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:"Accepted RRGH-hosted snow-depth and recent-precipitation snapshot manifest plus rasters, retaining source fetchedAtUtc.",
        processingMethod:"Copied exact RRGH-controlled Website derivative bytes from the frozen source commit into the protected Base package; every packaged file is SHA-256 indexed by NATIVE-MAP.json.",
        rightsBasis:"NOAA/NWS public U.S. government data through the LEG-DEC-0033 approved RRGH refreshable-weather path.",
        attributionOrDisclaimer:"NOAA / National Weather Service. Snapshot is last-known data with visible age and is not a trail-condition or safety guarantee.",
        outputVersion:$version,
        integritySHA256:$weatherManifestSha
      },
      {
        sourceID:"osm-community-local-context",
        sourceURL:$osmUrl,
        provider:"OpenStreetMap contributors via Geofabrik",
        vintageOrRetrievedAt:"Geofabrik Kentucky 2026-09-01 fixed snapshot",
        areaOfInterestOrSourceObjects:("All OSM highway-tagged ways plus hiking-route relations clipped to WGS84 bbox " + $bbox),
        processingMethod:"Downloaded fixed Kentucky PBF; local osmium bbox extract, tag filter and GeoJSON export. Public OSM tile servers and public Overpass are not used.",
        rightsBasis:"Open Database License (ODbL) 1.0 under LEG-DEC-0033 / LEG-REF-0036.",
        attributionOrDisclaimer:"© OpenStreetMap contributors, ODbL 1.0. OSM-derived database component remains logically/license-separated from proprietary RRGH route geometry; ODbL notice included in package.",
        outputVersion:$version,
        integritySHA256:$osmSha
      },
      {
        sourceID:"kgs-oil-gas-wells",
        sourceURL:$kgsUrl,
        provider:"Kentucky Geological Survey / University of Kentucky",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("Kentucky Oil and Gas Well Location dataset clipped to WGS84 bbox " + $bbox),
        processingMethod:"Downloaded provider ZIP; ogr2ogr geographic clip/reprojection to GeoJSON; provider kyog_info.txt and RRGH modification notice included.",
        rightsBasis:"LEG-DEC-0033 / LEG-REF-0038 and applicable KGS published dataset terms for planned commercial/offline use.",
        attributionOrDisclaimer:"Kentucky Geological Survey, University of Kentucky. Data are as-is with no warranty as to completeness, accuracy, location or well status; derivative is a clipped/converted RRGH package output.",
        outputVersion:$version,
        integritySHA256:$kgsSha
      }
    ]
  }' > "$MANIFEST"

jq -e   '.packageID == "gorge-base"
   and (.version | length > 0)
   and (.byteCount > 0)
   and (.sha256 | length == 64)
   and (.sources | length == 20)
   and all(.sources[];
     (.sourceID | length > 0)
     and (.sourceURL | length > 0)
     and (.provider | length > 0)
     and (.vintageOrRetrievedAt | length > 0)
     and (.areaOfInterestOrSourceObjects | length > 0)
     and (.processingMethod | length > 0)
     and (.rightsBasis | length > 0)
     and (.attributionOrDisclaimer | length > 0)
     and (.outputVersion | length > 0)
     and (.integritySHA256 | length == 64)
   )' "$MANIFEST" >/dev/null

echo "Gorge Base package built:"
echo "  version=$PACKAGE_VERSION"
echo "  bytes=$PACKAGE_BYTES"
echo "  sha256=$PACKAGE_SHA"
echo "  manifest=$MANIFEST"
echo "  package=$PACKAGE"
