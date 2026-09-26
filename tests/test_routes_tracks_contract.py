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
OSM_CACHE_PATH = ROOT / 'public/data/map/osm-informal-trails.geojson'
OSM_CACHE = json.loads(OSM_CACHE_PATH.read_text(encoding='utf-8'))
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
        self.assertIn('<section id="outdoor-safety-location-disclaimer">', terms)
        self.assertEqual(terms.count('id="outdoor-safety-location-disclaimer"'), 1)
        self.assertIn('Outdoor safety and location disclaimer', MAP)
        self.assertIn('copyright-and-terms/#outdoor-safety-location-disclaimer', MAP)
        self.assertIn('Interactive Maps and Map-Data Services', PRIVACY)
        self.assertIn('default map layers begin loading immediately', PRIVACY)
        self.assertIn('RRGH Hikes & Routes', explore)
        self.assertIn('RRGH Interactive Map', explore)
        self.assertIn('Kentucky LiDAR Guide', explore)

    def test_map_is_immediately_interactive_and_layer_mixable(self):
        self.assertNotIn('Load interactive map', MAP)
        for preset in ('hiking', 'terrain', 'aerial'):
            self.assertIn('data-map-preset="' + preset + '"', MAP)
        for trip_type in ('day-hike', 'backpacking', 'multi-day'):
            self.assertIn('data-route-trip-filter="' + trip_type + '"', MAP)
        for trail_status in ('official', 'mixed', 'off-trail'):
            self.assertIn('data-route-status-filter="' + trail_status + '"', MAP)
        for layer in (
            'kytopo', 'kyaerial-phase3', 'usgs-topo', 'ky-hillshade',
            'usfs-trails', 'usfs-roads', 'osm-informal-trails',
            'usfs-special-management', 'usfs-land-units'
        ):
            self.assertIn('data-map-layer="' + layer + '"', MAP)
            self.assertIn('data-opacity="' + layer + '"', MAP)
        self.assertIn('data-map-layer="usfs-wilderness"', MAP)
        self.assertNotIn('data-context-full-opacity="usfs-wilderness"', MAP)
        self.assertNotIn('Wilderness full opacity (100%)', MAP)
        self.assertNotIn('data-opacity="usfs-wilderness"', MAP)
        for always_on in ('RRGH routes', 'Route starts', 'Trailheads &amp; facilities', 'Landmarks &amp; viewpoints', 'County boundaries'):
            self.assertIn(always_on, MAP)
        self.assertIn('route-static-legend-grid', MAP)
        self.assertNotIn('Always shown', MAP)
        self.assertNotIn('data-map-layer="routes"', MAP)
        self.assertNotIn('data-map-layer="route-starts"', MAP)
        self.assertNotIn('data-map-layer="landmarks"', MAP)
        self.assertNotIn('data-map-layer="usfs-recreation-sites"', MAP)
        self.assertNotIn('data-map-layer="ky-counties"', MAP)
        self.assertNotIn('data-opacity="ky-counties"', MAP)
        self.assertIn('Fine tune layers', MAP)
        self.assertIn('value="100" data-opacity="usfs-trails"', MAP)
        self.assertIn('value="100" data-opacity="osm-informal-trails"', MAP)
        self.assertIn('value="100" data-opacity="usfs-roads"', MAP)
        self.assertIn("scrollWheelZoom: false", MAP)
        self.assertIn("minZoom: 8", MAP)
        self.assertIn("maxZoom: 20", MAP)

    def test_map_visual_legend_matches_cartography(self):
        for swatch in (
            'swatch-route', 'swatch-usfs-trail', 'swatch-usfs-road', 'swatch-county',
            'swatch-landmark', 'swatch-start', 'swatch-trailhead', 'swatch-informal'
        ):
            self.assertIn(swatch, MAP)
        self.assertIn("routePalette = [", MAP)
        self.assertIn("routeColorFor", MAP)
        self.assertIn("color: routeColor", MAP)
        self.assertIn("color: '#00c8ff'", MAP)
        self.assertIn("color: '#ffcf33'", MAP)
        self.assertIn("color: restricted ? '#f2f2f2' : '#b8f34a'", MAP)
        self.assertIn("color: '#665d4f'", MAP)
        self.assertIn("dashArray: '8 5'", MAP)
        self.assertIn("weight: 7.5", MAP)

    def test_map_has_everyday_controls_and_core_home_view(self):
        self.assertIn('data-sheet-open="search"', MAP)
        self.assertIn('data-map-action="locate"', MAP)
        self.assertIn('data-map-action="home"', MAP)
        self.assertIn('data-map-action="zoom-out"', MAP)
        self.assertIn('data-map-action="zoom-in"', MAP)
        self.assertIn("const homeCenter = L.latLng(37.8196836, -83.6396027)", MAP)
        self.assertIn("const homeZoom = 13", MAP)
        self.assertIn("const setHomeView = () => map.setView(homeCenter, homeZoom", MAP)
        self.assertIn("const syncViewportDiagnostics = () =>", MAP)
        self.assertIn("container.dataset.mapCenter", MAP)
        self.assertIn("container.dataset.mapNorthWest", MAP)
        self.assertIn("map.on('moveend', syncViewportDiagnostics)", MAP)
        self.assertIn("L.control.scale", MAP)
        self.assertIn('data-coordinate-card', MAP)
        self.assertIn('Copy coordinates', MAP)
        self.assertIn('navigator.geolocation.getCurrentPosition', MAP)
        self.assertIn('route-map-mobile-bar', MAP)
        self.assertIn("container.addEventListener('touchend'", MAP)

    def test_explore_is_a_route_browser_and_plan_is_single_entry_point(self):
        self.assertIn('data-sheet-open="explore"', MAP)
        self.assertIn('data-sheet-open="plan"', MAP)
        self.assertIn('const shouldClose = Boolean(panel && !panel.hidden)', MAP)
        self.assertIn('syncSheetButtons', MAP)
        self.assertIn('data-explore-route-list', MAP)
        self.assertIn('renderExploreRoutes', MAP)
        self.assertIn("pointerenter", MAP)
        self.assertIn("layer.bringToFront", MAP)
        self.assertNotIn('data-map-tool="explore"', MAP)
        self.assertIn('Explore RRGH routes', MAP)

    def test_map_share_builds_and_restores_stateful_permalinks(self):
        self.assertEqual(MAP.count('<button type="button" data-map-action="share">Share</button>'), 2)
        self.assertIn('data-map-sheet="share"', MAP)
        self.assertIn('data-share-url', MAP)
        self.assertIn('data-share-copy', MAP)
        self.assertIn("typeof navigator.share === 'function'", MAP)
        self.assertIn("navigator.share({ title, text, url })", MAP)
        self.assertIn("navigator.clipboard.writeText(url)", MAP)
        for param in ('rrghMap', 'rrghPreset', 'rrghLayers', 'rrghTrips', 'rrghStatus', 'rrghRoute'):
            self.assertIn(param, MAP)
        self.assertIn('const buildShareUrl = () =>', MAP)
        self.assertIn('const applySharedMapState = () =>', MAP)
        self.assertIn("line.on('click', () => { selectedRouteId = route.routeId; })", MAP)
        self.assertIn("if (mode === 'full' && !sharedViewApplied) setHomeView();", MAP)
        self.assertNotIn('locationLayer', MAP.split('const buildShareUrl = () =>', 1)[1].split('const showShareFallback', 1)[0])

    def test_map_routes_are_clickable_hiking_products(self):
        self.assertIn('routePopup', MAP)
        self.assertIn("route.distanceMi.toFixed(2)", MAP)
        self.assertIn("route.physicalDifficulty", MAP)
        self.assertIn("route.trailStatusDisplay", MAP)
        self.assertIn('View route guide', MAP)
        self.assertIn('Download GPX', MAP)
        self.assertIn('Parking / trailhead', MAP)
        self.assertIn('Route start · ', MAP)
        self.assertIn('TRAILHEAD', MAP)

    def test_map_has_mixed_snap_and_offtrail_planning_with_history(self):
        self.assertIn('data-map-tool="measure"', MAP)
        self.assertIn('data-map-tool="plan"', MAP)
        self.assertIn('data-map-tool="save"', MAP)
        self.assertNotIn('data-plan-segment-mode=', MAP)
        self.assertIn('data-plan-action="undo"', MAP)
        self.assertIn('data-plan-action="redo"', MAP)
        self.assertIn('planHistory', MAP)
        self.assertIn('commitPlanHistory', MAP)
        self.assertIn('restorePlanHistory', MAP)
        self.assertIn("mode: 'straight'", MAP)
        self.assertIn("mode: 'snap'", MAP)
        self.assertIn('buildAutoPlanSegment', MAP)
        self.assertIn('planSnapToleranceMeters = 90', MAP)
        self.assertIn('savePlanGpx', MAP)
        self.assertIn('shortestTrailPath', MAP)
        self.assertIn('nearestNode', MAP)
        self.assertIn('deletePlanSegment', MAP)
        self.assertIn("hitLine.on('contextmenu'", MAP)
        self.assertIn("const planningRenderer = L.svg({ pane: 'planning' })", MAP)
        self.assertGreaterEqual(MAP.count("renderer: planningRenderer"), 5)
        self.assertIn("className: 'rrgh-plan-segment-hit'", MAP)
        self.assertIn("hitElement.dataset.planSegmentIndex = String(segmentIndex)", MAP)
        self.assertIn('let segmentDragActive = false', MAP)
        self.assertIn("hitLine.on('mousedown'", MAP)
        self.assertIn("hitElement.addEventListener('mousedown'", MAP)
        self.assertIn("hitElement.addEventListener('pointerdown'", MAP)
        self.assertIn("hitElement.setPointerCapture(event.pointerId)", MAP)
        self.assertIn("window.addEventListener('mousemove', onMove, true)", MAP)
        self.assertIn("window.addEventListener('pointermove', onMove, true)", MAP)
        self.assertIn("window.addEventListener('mouseup', onEnd, true)", MAP)
        self.assertIn("window.addEventListener('pointerup', onEnd, true)", MAP)
        self.assertIn("window.addEventListener('pointercancel', onCancel, true)", MAP)
        self.assertIn('container.dataset.planDragSegment = String(segmentIndex)', MAP)
        self.assertIn("container.dataset.planDragMoved = 'true'", MAP)
        self.assertIn("container.dataset.planDragPreviewMode = snapped ? 'snap' : 'straight'", MAP)
        self.assertIn('let lastResolvedTarget: PlanPoint | null = null', MAP)
        self.assertIn('const resolvedDrop = lastResolvedTarget', MAP)
        self.assertIn('buildAutoPlanSegment(startStop, target)', MAP)
        self.assertIn('movePlanSegmentTarget', MAP)
        self.assertIn('data-plan-pan-pad', MAP)
        for direction in ('up', 'down', 'left', 'right'):
            self.assertIn('data-plan-pan-direction="' + direction + '"', MAP)
        self.assertIn('map.panBy', MAP)
        self.assertIn("if (planPanPad) planPanPad.hidden = tool !== 'plan'", MAP)
        self.assertNotIn('data-plan-pan aria-pressed', MAP)
        self.assertNotIn("let planPanMode = false", MAP)
        self.assertNotIn("✥ Resume route", MAP)
        self.assertNotIn('data-staging-copy-map-view', MAP)
        self.assertNotIn('Copy current map view', MAP)
        self.assertIn("application/gpx+xml", MAP)
        self.assertIn("RRGH-planned-route-", MAP)

    def test_planner_uses_official_roads_and_loaded_informal_paths(self):
        self.assertIn("for (const line of geometryLines(feature.geometry)) addSnapLine(line);", MAP)
        self.assertIn("Not used for route snapping", MAP)
        self.assertIn("Available for route snapping", MAP)
        self.assertIn("accessLower === 'no' || accessLower === 'private'", MAP)
        self.assertIn("bridgeNearbyEndpoints();", MAP)

    def test_map_layer_logic_matches_outdoor_planning_behavior(self):
        self.assertIn("hillshade: 180", MAP)
        self.assertIn("baseTopo: 200", MAP)
        self.assertIn("baseUsTopo: 210", MAP)
        self.assertIn("baseAerial: 220", MAP)
        self.assertIn("counties: 415", MAP)
        self.assertIn("routes: 440", MAP)
        self.assertIn("pane.style.mixBlendMode = 'multiply'", MAP)
        self.assertIn("id === 'kyaerial-phase3' && checkbox.checked", MAP)
        self.assertIn("setLayerControl('ky-hillshade', false)", MAP)
        self.assertIn("(id === 'kytopo' || id === 'usgs-topo' || id === 'ky-hillshade') && checkbox.checked", MAP)
        self.assertIn("setLayerControl('kyaerial-phase3', false)", MAP)
        self.assertIn("new Set(['Wolfe', 'Powell', 'Menifee', 'Lee'])", MAP)
        self.assertIn("map.setMaxBounds(paddedBounds)", MAP)
        self.assertIn("countyLayer.addTo(map)", MAP)
        self.assertIn("maxNativeZoom: source.maxNativeZoom", MAP)
        self.assertIn("maxNativeZoom: 16", LAYERS)
        self.assertIn("syncRouteFilters", MAP)
        self.assertIn("container.dataset.visibleRouteCount", MAP)
        self.assertIn("container.dataset.plannerNodeCount", MAP)
        self.assertIn("container.dataset.currentZoom", MAP)
        self.assertIn("name === 'hiking'", MAP)
        self.assertIn("name === 'terrain'", MAP)
        self.assertIn("setLayerControl('kytopo', true, 72)", MAP)
        self.assertGreaterEqual(MAP.count("setLayerControl('usgs-topo', true, 72)"), 2)
        self.assertIn('data-map-layer="usgs-topo" checked', MAP)
        self.assertIn("setLayerControl('ky-hillshade', true, 72)", MAP)
        self.assertIn("setLayerControl('usfs-wilderness', true)", MAP)
        self.assertNotIn('data-context-full-opacity="usfs-wilderness"', MAP)
        self.assertNotIn('Wilderness full opacity (100%)', MAP)
        self.assertNotIn('data-opacity="usfs-wilderness"', MAP)
        self.assertIn("slider.disabled = aerialActive", MAP)
        self.assertIn("for (const id of ['kytopo', 'usgs-topo', 'ky-hillshade'])", MAP)
        self.assertIn("aerialContextStyles", MAP)
        self.assertIn("color: '#ff4fd8'", MAP)
        self.assertIn("color: '#ffe14a'", MAP)
        self.assertIn("color: '#62ff9d'", MAP)
        self.assertIn("shell.dataset.aerialActive = String(aerialActive)", MAP)
        self.assertIn("setLayerControl('kytopo', false)", MAP)
        self.assertIn("setLayerControl('usgs-topo', false)", MAP)
        self.assertIn("(id === 'kytopo' || id === 'usgs-topo' || id === 'ky-hillshade') && checkbox.checked", MAP)

    def test_informal_trails_have_public_overpass_failover_and_default_on(self):
        self.assertIn('data-map-layer="osm-informal-trails" checked', MAP)
        self.assertIn('data-sheet-open="explore" disabled', MAP)
        self.assertGreaterEqual(MAP.count('data-sheet-open="plan" disabled'), 2)
        self.assertIn('setExplorePlanReady(false)', MAP)
        self.assertIn('setExplorePlanReady(true)', MAP)
        self.assertIn('Explore and Plan will unlock when trail data is ready.', MAP)
        self.assertIn('["informal"="yes"]', MAP)
        self.assertIn("data/map/osm-informal-trails.geojson", MAP)
        self.assertIn('https://overpass.maprva.org/api/interpreter', MAP)
        self.assertIn('https://overpass.private.coffee/api/interpreter', MAP)
        self.assertIn('https://overpass-api.de/api/interpreter', MAP)
        self.assertIn('https://maps.mail.ru/osm/tools/overpass/api/interpreter', MAP)
        self.assertIn("method: 'POST'", MAP)
        self.assertIn('Promise.any', MAP)
        self.assertIn('15000', MAP)
        self.assertIn('© OpenStreetMap contributors', MAP)
        self.assertIn("window.setTimeout(() => {", MAP)
        self.assertIn("void loadInformalTrails();", MAP)
        self.assertIn("container.dataset.informalTrailSource = 'rrgh-cache'", MAP)
        self.assertIn('RRGH-hosted cache derived from OpenStreetMap data', PRIVACY)
        self.assertIn('planner may snap to displayed community/informal paths', TERMS)
        self.assertIn('do not substantially match the authoritative USDA Forest Service trail geometry', TERMS)

    def test_cached_osm_candidates_are_nonempty_and_geographically_bounded(self):
        self.assertEqual(OSM_CACHE.get('type'), 'FeatureCollection')
        self.assertGreater(len(OSM_CACHE.get('features', [])), 50)
        meta = OSM_CACHE.get('rrgh_cache', {})
        self.assertTrue(meta.get('bounds_clipped'))
        self.assertEqual(meta.get('bbox'), [37.45, -83.93, 38.05, -83.25])
        classifications = {feature.get('properties', {}).get('rrgh_classification') for feature in OSM_CACHE['features']}
        self.assertIn('community-candidate', classifications)
        south, west, north, east = meta['bbox']
        for feature in OSM_CACHE['features']:
            coords = feature.get('geometry', {}).get('coordinates', [])
            self.assertGreaterEqual(len(coords), 2)
            for lon, lat in coords:
                self.assertGreaterEqual(lat, south)
                self.assertLessEqual(lat, north)
                self.assertGreaterEqual(lon, west)
                self.assertLessEqual(lon, east)

    def test_land_management_defaults_on_and_counties_are_fixed_context(self):
        for layer in ('usfs-wilderness', 'usfs-special-management', 'usfs-land-units'):
            self.assertIn('data-map-layer="' + layer + '" checked', MAP)
        self.assertIn("loadLandContext('usfs-wilderness')", MAP)
        self.assertIn("loadLandContext('usfs-special-management')", MAP)
        self.assertIn("loadLandContext('usfs-land-units')", MAP)
        self.assertIn('<span>County boundaries</span>', MAP)
        self.assertNotIn('Always shown', MAP)
        self.assertIn("const countiesVisible = map.getZoom() <= 13", MAP)

    def test_map_reading_help_and_legal_access_context_are_present(self):
        self.assertIn('How to read this map — 30-second guide', MAP)
        self.assertIn('Closer lines mean steeper terrain', MAP)
        self.assertIn('Advanced Map Details', MAP)
        self.assertNotIn('Map nerd details', MAP)
        self.assertIn('Terrain relief (LiDAR)', MAP)
        self.assertIn('Property boundaries are not shown; this map does not establish legal access.', MAP)
        self.assertIn('Before you go: check closures, road access &amp; conditions', MAP)
        self.assertIn('Outdoor safety and location disclaimer', MAP)
        self.assertIn('If you choose “My location,”', PRIVACY)

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
