#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-/tmp/rrgh-gorge-base}"
PACKAGE_VERSION="${2:-2026.10.06.1}"
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
mkdir -p   "$ROOT/layers/terrain"   "$ROOT/layers/hydrography"   "$ROOT/layers/roads"   "$ROOT/layers/forest"   "$ROOT/layers/osm"   "$ROOT/layers/kgs"   "$ROOT/documentation/kgs"   "$ROOT/documentation/osm"   "$DOWNLOADS"

for command in curl jq unzip ogr2ogr ogrinfo osmium sha256sum gzip tar; do
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

# 1. Terrain / hillshade — exact KyFromAbove ImageServer export, bounded to RRGH AOI.
KYFROMABOVE_SERVICE="https://kyraster.ky.gov/arcgis/rest/services/ElevationServices/Ky_DEM_KYAPED_2FT_Phase3_MultiDirectionalHillshade_WGS84WM/ImageServer"
KYFROMABOVE_OUT="$ROOT/layers/terrain/kyfromabove-hillshade.tif"
curl --fail --location --retry 4 --retry-all-errors   --get "$KYFROMABOVE_SERVICE/exportImage"   --data-urlencode "bbox=$BBOX"   --data-urlencode "bboxSR=4326"   --data-urlencode "imageSR=3857"   --data-urlencode "size=4096,3072"   --data-urlencode "format=tiff"   --data-urlencode "interpolation=RSP_BilinearInterpolation"   --data-urlencode "f=image"   -o "$KYFROMABOVE_OUT"
test -s "$KYFROMABOVE_OUT"

# 2. USGS NHDPlus High Resolution, HUC4 0510 — fixed downloadable snapshot.
USGS_NHD_URL="https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHDPlus/HU4/HighResolution/GDB/NHDPLUS_H_0510_HU4_GDB.zip"
USGS_ZIP="$DOWNLOADS/NHDPLUS_H_0510_HU4_GDB.zip"
download "$USGS_NHD_URL" "$USGS_ZIP"
mkdir -p "$DOWNLOADS/nhd"
unzip -q "$USGS_ZIP" -d "$DOWNLOADS/nhd"
NHD_GDB="$(find "$DOWNLOADS/nhd" -type d -name '*.gdb' | head -n 1)"
test -n "$NHD_GDB"

FLOW_LAYER="$(ogrinfo -ro "$NHD_GDB" 2>/dev/null | sed -n 's/^[0-9][0-9]*: \([^ ]*NHDFlowline[^ ]*\).*/\1/p' | head -n 1)"
WATER_LAYER="$(ogrinfo -ro "$NHD_GDB" 2>/dev/null | sed -n 's/^[0-9][0-9]*: \([^ ]*NHDWaterbody[^ ]*\).*/\1/p' | head -n 1)"
test -n "$FLOW_LAYER"
test -n "$WATER_LAYER"

ogr2ogr -f GeoJSON   -t_srs EPSG:4326   -spat "$WEST" "$SOUTH" "$EAST" "$NORTH"   -spat_srs EPSG:4326   "$ROOT/layers/hydrography/usgs-nhd-flowline.geojson"   "$NHD_GDB" "$FLOW_LAYER"
ogr2ogr -f GeoJSON   -t_srs EPSG:4326   -spat "$WEST" "$SOUTH" "$EAST" "$NORTH"   -spat_srs EPSG:4326   "$ROOT/layers/hydrography/usgs-nhd-waterbody.geojson"   "$NHD_GDB" "$WATER_LAYER"

# 3. 2026 Census TIGER/Line county Roads — Powell, Wolfe, Menifee, Lee.
CENSUS_BASE="https://www2.census.gov/geo/tiger/TIGER2026/ROADS"
: > "$DOWNLOADS/census-features.ndjson"
for fips in 21129 21165 21197 21237; do
  ZIP="$DOWNLOADS/tl_2026_${fips}_roads.zip"
  DIR="$DOWNLOADS/census-${fips}"
  download "$CENSUS_BASE/tl_2026_${fips}_roads.zip" "$ZIP"
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

# Freeze per-output source integrity before creating the package archive.
KY_SHA="$(hash_file "$KYFROMABOVE_OUT")"
NHD_FLOW_SHA="$(hash_file "$ROOT/layers/hydrography/usgs-nhd-flowline.geojson")"
NHD_WATER_SHA="$(hash_file "$ROOT/layers/hydrography/usgs-nhd-waterbody.geojson")"
CENSUS_SHA="$(hash_file "$ROOT/layers/roads/census-tiger-roads.geojson")"
USFS_TRAILS_SHA="$(hash_file "$ROOT/layers/forest/usfs-nfs-trails.geojson")"
USFS_ROADS_SHA="$(hash_file "$ROOT/layers/forest/usfs-nfs-roads.geojson")"
USFS_OWNER_SHA="$(hash_file "$ROOT/layers/forest/usfs-basic-ownership.geojson")"
OSM_SHA="$(hash_file "$ROOT/layers/osm/osm-community-local-context.geojson")"
KGS_SHA="$(hash_file "$ROOT/layers/kgs/kgs-oil-gas-wells.geojson")"
OSM_SOURCE_SHA="$(hash_file "$OSM_SOURCE")"
KGS_SOURCE_SHA="$(hash_file "$KGS_ZIP")"
USGS_SOURCE_SHA="$(hash_file "$USGS_ZIP")"

jq -n   --arg packageVersion "$PACKAGE_VERSION"   --arg builtAt "$RETRIEVED_AT"   --arg bbox "$BBOX"   --arg osmSourceSha "$OSM_SOURCE_SHA"   --arg kgsSourceSha "$KGS_SOURCE_SHA"   --arg usgsSourceSha "$USGS_SOURCE_SHA"   '{
    packageID:"gorge-base",
    packageVersion:$packageVersion,
    builtAt:$builtAt,
    areaOfInterest:{bboxWgs84:$bbox,note:"RRGH supported-area build AOI; not a legal boundary"},
    sourceArchiveIntegrity:{
      geofabrikKentuckyPbfSHA256:$osmSourceSha,
      kgsOilGasZipSHA256:$kgsSourceSha,
      usgsNhdPlusHuc4ZipSHA256:$usgsSourceSha
    },
    exclusions:{
      protectedRouteGeometry:"Delivered as separately entitlement-authorized route packages; not embedded in Gorge Base.",
      streamStats:"Paid connected-only under LEG-DEC-0033; no offline substitute.",
      parcels:"Excluded pending exact authorized source.",
      gaiaCalTopoPublicTiles:"Excluded; no proprietary/public tile scraping.",
      scheduledWeather:"Separate timestamped refresh package/workflow; not silently represented as static Gorge Base data."
    }
  }' > "$ROOT/BUILD-PROVENANCE.json"

# Deterministic archive framing for these exact built files.
(
  cd "$ROOT"
  tar --sort=name     --mtime='UTC 2026-10-06 00:00:00'     --owner=0 --group=0 --numeric-owner     -cf - .
) | gzip -n > "$PACKAGE"

PACKAGE_SHA="$(hash_file "$PACKAGE")"
PACKAGE_BYTES="$(stat -c '%s' "$PACKAGE")"

# External manifest shape is exactly the Lane 21 OfflinePackageManifest contract.
jq -n   --arg packageID "gorge-base"   --arg version "$PACKAGE_VERSION"   --argjson byteCount "$PACKAGE_BYTES"   --arg sha256 "$PACKAGE_SHA"   --arg retrievedAt "$RETRIEVED_AT"   --arg bbox "$BBOX"   --arg kyUrl "$KYFROMABOVE_SERVICE"   --arg kySha "$KY_SHA"   --arg nhdUrl "$USGS_NHD_URL"   --arg nhdFlowSha "$NHD_FLOW_SHA"   --arg nhdWaterSha "$NHD_WATER_SHA"   --arg censusUrl "$CENSUS_BASE"   --arg censusSha "$CENSUS_SHA"   --arg usfsTrails "$USFS_TRAILS"   --arg usfsTrailsSha "$USFS_TRAILS_SHA"   --arg usfsRoads "$USFS_ROADS"   --arg usfsRoadsSha "$USFS_ROADS_SHA"   --arg usfsOwnership "$USFS_OWNERSHIP"   --arg usfsOwnershipSha "$USFS_OWNER_SHA"   --arg osmUrl "$OSM_URL"   --arg osmSha "$OSM_SHA"   --arg kgsUrl "$KGS_URL"   --arg kgsSha "$KGS_SHA"   '{
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
        provider:"U.S. Geological Survey / The National Map",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("NHDPlus High Resolution HUC4 0510 NHDFlowline clipped to WGS84 bbox " + $bbox),
        processingMethod:"Downloaded fixed NHDPlus HR HU4 geodatabase package; ogr2ogr bounded clip/reprojection to GeoJSON.",
        rightsBasis:"U.S. federal public-domain geospatial data; LEG-DEC-0033 / LEG-REF-0025.",
        attributionOrDisclaimer:"USGS / The National Map; fixed contextual hydrography snapshot, not live regulatory or access data.",
        outputVersion:$version,
        integritySHA256:$nhdFlowSha
      },
      {
        sourceID:"usgs-nhdplus-waterbody",
        sourceURL:$nhdUrl,
        provider:"U.S. Geological Survey / The National Map",
        vintageOrRetrievedAt:$retrievedAt,
        areaOfInterestOrSourceObjects:("NHDPlus High Resolution HUC4 0510 NHDWaterbody clipped to WGS84 bbox " + $bbox),
        processingMethod:"Downloaded fixed NHDPlus HR HU4 geodatabase package; ogr2ogr bounded clip/reprojection to GeoJSON.",
        rightsBasis:"U.S. federal public-domain geospatial data; LEG-DEC-0033 / LEG-REF-0025.",
        attributionOrDisclaimer:"USGS / The National Map; fixed contextual hydrography snapshot, not live regulatory or access data.",
        outputVersion:$version,
        integritySHA256:$nhdWaterSha
      },
      {
        sourceID:"census-tiger-roads",
        sourceURL:$censusUrl,
        provider:"U.S. Census Bureau",
        vintageOrRetrievedAt:"2026 TIGER/Line Roads",
        areaOfInterestOrSourceObjects:("Lee 21129, Menifee 21165, Powell 21197, Wolfe 21237 county Roads clipped to WGS84 bbox " + $bbox),
        processingMethod:"Downloaded official 2026 county Roads shapefiles; ogr2ogr bounded clip/reprojection; merged as one GeoJSON FeatureCollection.",
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
   and (.sources | length == 9)
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
