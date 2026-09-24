import hashlib
import json
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ROUTE = json.loads((ROOT / 'src/data/routes/skybridge-arch.json').read_text(encoding='utf-8'))
GPX = ROOT / 'public/downloads/routes/Skybridge_Arch_APPROVED_v1.gpx'
GEO = ROOT / 'public/data/routes/skybridge-arch-v1.geojson'
CONTENT_CONFIG = (ROOT / 'src/content.config.ts').read_text(encoding='utf-8')
LAYERS = (ROOT / 'src/data/map/layers.ts').read_text(encoding='utf-8')
MAP = (ROOT / 'src/components/RouteMap.astro').read_text(encoding='utf-8')
NOTICE = (ROOT / 'src/components/RouteNotice.astro').read_text(encoding='utf-8')
GPX_COMPONENT = (ROOT / 'src/components/GpxDownload.astro').read_text(encoding='utf-8')
DETAIL = (ROOT / 'src/pages/routes/[slug].astro').read_text(encoding='utf-8')
INDEX = (ROOT / 'src/pages/routes/index.astro').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/components/RouteLibrary.astro').read_text(encoding='utf-8')
FULL_MAP = (ROOT / 'src/pages/routes/map.astro').read_text(encoding='utf-8')
GUIDE = (ROOT / 'src/pages/guides/kentucky-lidar.astro').read_text(encoding='utf-8')
PRIVACY = (ROOT / 'src/pages/privacy.astro').read_text(encoding='utf-8')
TERMS = (ROOT / 'src/pages/copyright-and-terms.astro').read_text(encoding='utf-8')
GENERATOR = (ROOT / 'scripts/generate-route-elevation.mjs').read_text(encoding='utf-8')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RoutesTracksContractTests(unittest.TestCase):
    def test_skybridge_public_package_identity(self):
        self.assertEqual(ROUTE['routeId'], 'RTE-0001')
        self.assertEqual(ROUTE['publicationStatus'], 'Approved — Publication Ready')
        self.assertEqual(ROUTE['publicationClass'], 'A')
        self.assertEqual(ROUTE['distanceMi'], 0.784)
        self.assertEqual(sha256(GPX), '2469c85ebaddd3e701ba6dc8eea3664d90a0667dcd86f2aab43ae1445986830d')
        self.assertEqual(sha256(GEO), '123fdb57e1142299f86c714367cc466b70f18fa90cfbaabb92b0d9ced157dc66')

    def test_approved_gpx_is_public_hygiene_only(self):
        text = GPX.read_text(encoding='utf-8')
        self.assertIn('version="1.1"', text)
        self.assertEqual(len(re.findall(r'<trkpt\b', text)), 100)
        self.assertEqual(len(re.findall(r'<wpt\b', text)), 2)
        self.assertNotRegex(text, r'<time>|<ele>|Gaia|PROPOSED|RAW')
        root = ET.fromstring(text)
        ns = {'g': 'http://www.topografix.com/GPX/1/1'}
        names = [w.find('g:name', ns).text for w in root.findall('g:wpt', ns)]
        self.assertEqual(names, ['Skybridge Arch', 'Turnaround Overlook'])

    def test_public_waypoints_match_approved_geometry_exactly(self):
        geo = json.loads(GEO.read_text(encoding='utf-8'))
        points = [f for f in geo['features'] if f['geometry']['type'] == 'Point']
        self.assertEqual(len(points), 2)
        expected = {
            'WP-0001': ('Skybridge Arch', 37.81886, -83.57903),
            'WP-0002': ('Turnaround Overlook', 37.81913, -83.57684),
        }
        for feature in points:
            wid = feature['properties']['waypointId']
            name, lat, lon = expected[wid]
            self.assertEqual(feature['properties']['name'], name)
            self.assertEqual(feature['geometry']['coordinates'], [lon, lat])
        self.assertEqual(len(ROUTE['publicWaypoints']), 2)

    def test_public_package_excludes_private_and_sensitive_lane19_data(self):
        combined = '\n'.join([
            (ROOT / 'src/data/routes/skybridge-arch.json').read_text(encoding='utf-8'),
            GPX.read_text(encoding='utf-8'),
            GEO.read_text(encoding='utf-8'),
        ])
        for prohibited in (
            'drive.google.com', 'RAW Gaia', 'PROPOSED', '1w0Uq5LPJxmVKEQCqJ6SIvdSGOEAnP_lM',
            '1PaL0N8YX811a7q0n5X7rmvT4DYVil6HK', 'eagle nest', "eagle's nest", 'Lane 19'
        ):
            self.assertNotIn(prohibited.lower(), combined.lower())

    def test_schema_is_data_only_and_supports_zero_or_many_waypoints(self):
        self.assertIn("glob({ pattern: '**/*.json', base: './src/data/routes' })", CONTENT_CONFIG)
        self.assertIn("publicWaypoints: z.array(waypointSchema)", CONTENT_CONFIG)
        self.assertIn("publicationClass: z.enum(['A', 'B', 'C'])", CONTENT_CONFIG)
        self.assertNotIn("publicationClass: z.enum(['A', 'B', 'C', 'D'])", CONTENT_CONFIG)

    def test_map_source_registry_includes_real_planning_context(self):
        for source in (
            'Ky_KyTopo_Map_Series_WGS84WM',
            'Ky_Imagery_Phase3_3IN_WGS84WM',
            'Ky_MultiDirectional_Hillshade_WGS84WM',
            'USGSTopo',
            'EDW_TrailNFSPublishWithDataStatus_01',
            'EDW_RoadBasic_01',
            'Ky_CountyLines_WGS84WM',
            'EDW_RecInfraRecreationSites_02',
            'EDW_Wilderness_01',
            'EDW_SpecialInterestManagementArea_01',
            'EDW_NFSLandUnit_01',
        ):
            self.assertIn(source, LAYERS)
        self.assertIn("id: 'usfs-trails'", LAYERS)
        self.assertIn("id: 'usfs-roads'", LAYERS)
        self.assertIn("id: 'ky-counties'", LAYERS)
        self.assertIn("id: 'usfs-recreation-sites'", LAYERS)
        self.assertIn("id: 'usfs-wilderness'", LAYERS)
        self.assertIn("id: 'usfs-special-management'", LAYERS)
        self.assertIn("id: 'usfs-land-units'", LAYERS)
        self.assertIn("id: 'osm-informal-trails'", LAYERS)
        self.assertIn("id: 'parcel-private-property'", LAYERS)
        parcel = LAYERS.split("id: 'parcel-private-property'", 1)[1].split("}", 1)[0]
        self.assertIn('enabled: false', parcel)
        self.assertNotIn('Gaia', LAYERS)
        self.assertNotIn('CalTopo', LAYERS)

    def test_elevation_is_build_time_usgs_3dep_only(self):
        self.assertIn('3DEPElevation/ImageServer/getSamples', GENERATOR)
        self.assertEqual(ROUTE['elevation']['sampleCount'], 100)
        self.assertIn('RSP_BilinearInterpolation', GENERATOR)
        self.assertIn('Build-time only', LAYERS)
        self.assertNotIn('elevation.nationalmap.gov', MAP)

    def test_route_pages_and_legal_controls_are_present(self):
        self.assertIn("getCollection('routes')", INDEX)
        self.assertIn("getCollection('routes')", DETAIL)
        self.assertIn('RouteNotice', DETAIL)
        self.assertIn('GpxDownload', DETAIL)
        self.assertIn('ElevationProfile', DETAIL)
        self.assertIn('Dataset', DETAIL)
        self.assertIn('DataDownload', DETAIL)
        self.assertIn('Route information is not a safety or access guarantee.', NOTICE)
        self.assertIn('By downloading this GPX file, you acknowledge', GPX_COMPONENT)
        self.assertIn('GPX Download License and site Terms', GPX_COMPONENT)
        terms = (ROOT / 'src/pages/copyright-and-terms.astro').read_text(encoding='utf-8')
        explore = (ROOT / 'src/data/explore.ts').read_text(encoding='utf-8')
        self.assertIn('id="gpx-download-license"', terms)
        self.assertIn('Routes, Maps, GPS Tracks, and Location Information', terms)
        self.assertIn('Interactive Maps and Map-Data Services', PRIVACY)
        self.assertIn('default map layers begin loading immediately', PRIVACY)
        self.assertIn('RRGH Hikes & Routes', explore)
        self.assertIn('RRGH Interactive Map', explore)
        self.assertIn('Kentucky LiDAR Guide', explore)

    def test_map_is_immediately_interactive_and_layer_mixable(self):
        self.assertNotIn('Load interactive map', MAP)
        self.assertNotIn('No external map tiles are requested until', MAP)
        for preset in ('hiking', 'terrain', 'aerial'):
            self.assertIn('data-map-preset="' + preset + '"', MAP)
        self.assertIn('<strong>Hiking</strong>', MAP)
        self.assertIn('<strong>Terrain</strong>', MAP)
        self.assertIn('<strong>Aerial</strong>', MAP)
        for trip_type in ('day-hike', 'backpacking', 'multi-day'):
            self.assertIn('data-route-trip-filter="' + trip_type + '"', MAP)
        for trail_status in ('official', 'mixed', 'off-trail'):
            self.assertIn('data-route-status-filter="' + trail_status + '"', MAP)
        for layer in (
            'kytopo', 'kyaerial-phase3', 'usgs-topo', 'ky-hillshade',
            'usfs-trails', 'usfs-roads', 'ky-counties', 'routes', 'route-starts',
            'landmarks', 'usfs-recreation-sites', 'osm-informal-trails',
            'usfs-wilderness', 'usfs-special-management', 'usfs-land-units'
        ):
            self.assertIn('data-map-layer="' + layer + '"', MAP)
            self.assertIn('data-opacity="' + layer + '"', MAP)
        self.assertIn('Fine tune layers', MAP)
        self.assertIn('type="range"', MAP)
        self.assertIn("credentials: 'omit'", MAP)
        self.assertIn("keyboard: true", MAP)
        self.assertIn("scrollWheelZoom: false", MAP)
        self.assertIn("minZoom: 6", MAP)
        self.assertIn("maxZoom: 20", MAP)
        self.assertNotIn("map.setMinZoom(map.getZoom())", MAP)

    def test_map_visual_legend_matches_cartography(self):
        for swatch in (
            'swatch-route', 'swatch-usfs-trail', 'swatch-usfs-road', 'swatch-county',
            'swatch-landmark', 'swatch-start', 'swatch-trailhead', 'swatch-informal'
        ):
            self.assertIn(swatch, MAP)
        self.assertIn("color: '#0d6654'", MAP)
        self.assertIn("color: '#5d6387'", MAP)
        self.assertIn("color: '#8a6a46'", MAP)
        self.assertIn("dashArray: '7 6'", MAP)
        self.assertIn("weight: 7.5", MAP)

    def test_map_has_everyday_controls_and_cartographic_context(self):
        self.assertIn('data-sheet-open="search"', MAP)
        self.assertIn('data-map-action="locate"', MAP)
        self.assertIn('data-map-action="home"', MAP)
        self.assertIn("L.control.scale", MAP)
        self.assertIn('data-coordinate-card', MAP)
        self.assertIn('Copy coordinates', MAP)
        self.assertIn('toUtm', MAP)
        self.assertIn('navigator.geolocation.getCurrentPosition', MAP)
        self.assertIn('data-map-search', MAP)
        self.assertIn('route-map-mobile-bar', MAP)
        self.assertIn('Search</button>', MAP)
        self.assertIn('Layers</button>', MAP)
        self.assertIn('Plan</button>', MAP)
        self.assertIn("container.addEventListener('touchend'", MAP)
        self.assertIn('Map data:', MAP)
        self.assertIn('Property boundaries are not shown; this map does not establish legal access.', MAP)
        self.assertIn('Before you go: check closures, road access &amp; conditions', MAP)

    def test_map_routes_are_clickable_hiking_products(self):
        self.assertIn('routePopup', MAP)
        self.assertIn("route.distanceMi.toFixed(2)", MAP)
        self.assertIn("route.physicalDifficulty", MAP)
        self.assertIn("route.trailStatusDisplay", MAP)
        self.assertIn('View route guide', MAP)
        self.assertIn('Download GPX', MAP)
        self.assertIn('Parking / trailhead', MAP)
        self.assertIn('Route start · ', MAP)
        self.assertIn("id: 'usfs-recreation-sites'", LAYERS)
        self.assertIn('TRAILHEAD', MAP)

    def test_map_has_measurement_and_trail_snap_planning(self):
        self.assertIn('data-map-tool="explore"', MAP)
        self.assertIn('data-map-tool="measure"', MAP)
        self.assertIn('data-map-tool="plan"', MAP)
        self.assertIn('data-map-tool="save"', MAP)
        self.assertIn('Measure distance', MAP)
        self.assertIn('Build trail route', MAP)
        self.assertIn('Export GPX', MAP)
        self.assertIn('savePlanGpx', MAP)
        self.assertIn('shortestTrailPath', MAP)
        self.assertIn('nearestNode', MAP)
        self.assertIn('within about 90 m', MAP)
        self.assertIn('Community / Informal trails are not used for routing', MAP)
        self.assertIn('trail-route planning', FULL_MAP)

    def test_map_layer_logic_matches_outdoor_planning_behavior(self):
        self.assertIn("hillshade: 180", MAP)
        self.assertIn("baseTopo: 200", MAP)
        self.assertIn("baseUsTopo: 210", MAP)
        self.assertIn("baseAerial: 220", MAP)
        self.assertIn("pane.style.mixBlendMode = 'multiply'", MAP)
        self.assertIn("id === 'kyaerial-phase3' && checkbox.checked", MAP)
        self.assertIn("setLayerControl('ky-hillshade', false)", MAP)
        self.assertIn("id === 'ky-hillshade' && checkbox.checked", MAP)
        self.assertIn("setLayerControl('kyaerial-phase3', false)", MAP)
        self.assertIn("map.fitBounds([[37.58, -83.93], [38.04, -83.25]]", MAP)
        self.assertIn("new Set(['Wolfe', 'Powell', 'Menifee', 'Lee'])", MAP)
        self.assertIn("map.setMaxBounds(paddedBounds)", MAP)
        self.assertIn('data-map-layer="ky-counties" />', MAP)
        self.assertIn('value="32" data-opacity="ky-counties"', MAP)
        self.assertIn("maxNativeZoom: source.maxNativeZoom", MAP)
        self.assertIn("maxNativeZoom: 16", LAYERS)
        self.assertIn("Four-county planning view for Wolfe, Powell, Menifee, and Lee counties.", FULL_MAP)
        self.assertIn("syncRouteFilters", MAP)
        self.assertIn("container.dataset.visibleRouteCount", MAP)
        self.assertIn("container.dataset.visibleRouteStartCount", MAP)
        self.assertIn("container.dataset.plannerNodeCount", MAP)
        self.assertIn("container.dataset.currentZoom", MAP)
        self.assertIn("Math.ceil(from.distanceTo(to) / 30)", MAP)
        self.assertIn("application/gpx+xml", MAP)
        self.assertIn("RRGH-planned-route-", MAP)
        self.assertIn("name === 'hiking'", MAP)
        self.assertIn("name === 'terrain'", MAP)
        self.assertIn("setLayerControl('kytopo', true, 70)", MAP)
        self.assertIn("setLayerControl('ky-hillshade', true, 45)", MAP)

    def test_informal_trails_are_explicit_optional_osm_data(self):
        self.assertIn('Community / Informal trails', MAP)
        self.assertIn('["informal"="yes"]', MAP)
        self.assertIn('https://overpass-api.de/api/interpreter', MAP)
        self.assertIn('© OpenStreetMap contributors', MAP)
        self.assertIn('Not an official Forest Service trail', MAP)
        self.assertIn('An informal path is not proof of legal access.', LAYERS)
        self.assertIn('Community / Informal Trails layer', TERMS)
        self.assertIn('Open Database License (ODbL)', TERMS)
        self.assertIn('public Overpass API', PRIVACY)

    def test_land_management_and_map_reading_help_are_present(self):
        self.assertIn('Wilderness boundaries', MAP)
        self.assertIn('Special management areas', MAP)
        self.assertIn('National Forest land units', MAP)
        self.assertIn('How to read this map — 30-second guide', MAP)
        self.assertIn('Closer lines mean steeper terrain', MAP)
        self.assertIn('Map nerd details', MAP)
        self.assertIn('Terrain relief (LiDAR)', MAP)
        self.assertIn('Kentucky LiDAR', MAP)

    def test_location_terms_and_privacy_are_explicit(self):
        self.assertIn('location reported by your browser or device', TERMS)
        self.assertIn('Property and parcel boundaries are not displayed', TERMS)
        self.assertIn('If you choose “My location,”', PRIVACY)
        self.assertIn('does not intentionally transmit or store the precise device coordinates', PRIVACY)
        self.assertIn('does not send the search text to a general-purpose external geocoding service', PRIVACY)

    def test_public_route_ui_avoids_internal_workflow_language(self):
        public_ui = '\n'.join([DETAIL, INDEX, LIBRARY, FULL_MAP, MAP, (ROOT / 'src/components/ElevationProfile.astro').read_text(encoding='utf-8')])
        for prohibited in (
            'Publication Ready',
            'Lane 19',
            'Approved public waypoints',
            'Approved waypoints',
            'current Lane 19-approved route package',
            'Approved route shape',
            'approved route geometry',
        ):
            self.assertNotIn(prohibited, public_ui)
        self.assertIn('Landmarks &amp; viewpoints', DETAIL)
        self.assertIn('Map &amp; route data sources', DETAIL)

    def test_lidar_guide_keeps_gaia_caltopo_as_education_only(self):
        self.assertIn('Kentucky LiDAR &amp; Custom Map Sources', GUIDE)
        self.assertIn('Gaia GPS', GUIDE)
        self.assertIn('CalTopo', GUIDE)
        self.assertIn('does not publish or redistribute Gaia proprietary/Premium overlays', GUIDE)
        self.assertIn('Do not copy or rehost CalTopo proprietary map tiles', GUIDE)


if __name__ == '__main__':
    unittest.main()
