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
FULL_MAP = (ROOT / 'src/pages/routes/map.astro').read_text(encoding='utf-8')
GUIDE = (ROOT / 'src/pages/guides/kentucky-lidar.astro').read_text(encoding='utf-8')
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
            '1PaL0N8YX811a7q0n5X7rmvT4DYVil6HK', 'eagle nest', "eagle's nest"
        ):
            self.assertNotIn(prohibited.lower(), combined.lower())

    def test_schema_is_data_only_and_supports_zero_or_many_waypoints(self):
        self.assertIn("glob({ pattern: '**/*.json', base: './src/data/routes' })", CONTENT_CONFIG)
        self.assertIn("publicWaypoints: z.array(waypointSchema)", CONTENT_CONFIG)
        self.assertIn("publicationClass: z.enum(['A', 'B', 'C'])", CONTENT_CONFIG)
        self.assertNotIn("publicationClass: z.enum(['A', 'B', 'C', 'D'])", CONTENT_CONFIG)

    def test_map_source_registry_enables_only_approved_browser_sources(self):
        for source in ('KyTopo', 'Ky_Imagery_Phase3_3IN_WGS84WM', 'Ky_MultiDirectional_Hillshade_WGS84WM', 'USGSTopo'):
            self.assertIn(source, LAYERS)
        self.assertIn("id: 'parcel-private-property'", LAYERS)
        parcel = LAYERS.split("id: 'parcel-private-property'", 1)[1].split("}", 1)[0]
        self.assertIn('enabled: false', parcel)
        self.assertIn("id: 'usfs-reference-snapshots'", LAYERS)
        self.assertNotIn('Gaia', LAYERS)
        self.assertNotIn('CalTopo', LAYERS)

    def test_elevation_is_build_time_usgs_3dep_only(self):
        self.assertIn('3DEPElevation/ImageServer/getSamples', GENERATOR)
        self.assertIn("sampleCount:100", (ROOT / 'src/data/routes/skybridge-arch.json').read_text(encoding='utf-8').replace(' ', '').replace('\n',''))
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

    def test_map_accessibility_and_deliberate_external_loading(self):
        self.assertIn('No external map tiles are requested until you load the interactive map.', MAP)
        self.assertIn('Load interactive map', MAP)
        self.assertIn("alt: name", MAP)
        self.assertIn("keyboard: true", MAP)
        self.assertIn("scrollWheelZoom: mode === 'full'", MAP)
        self.assertIn("map.getZoom() >= 14", MAP)
        self.assertIn('Parcel / Private Property', LAYERS)

    def test_full_map_presets_and_filters_exist(self):
        for label in ('Simple', 'Terrain', 'Route Planning', 'Land & Access', 'All Layers'):
            self.assertIn(label, MAP)
        for label in ('Day hikes', 'Backpacking', 'Multi-day', 'Official / on-trail', 'Mixed', 'Selected off-trail'):
            self.assertIn(label, MAP)
        self.assertIn('Interactive Hikes &amp; Routes Map', FULL_MAP)

    def test_lidar_guide_keeps_gaia_caltopo_as_education_only(self):
        self.assertIn('Kentucky LiDAR &amp; Custom Map Sources', GUIDE)
        self.assertIn('Gaia GPS', GUIDE)
        self.assertIn('CalTopo', GUIDE)
        self.assertIn('does not publish or redistribute Gaia proprietary/Premium overlays', GUIDE)
        self.assertIn('Do not copy or rehost CalTopo proprietary map tiles', GUIDE)

if __name__ == '__main__':
    unittest.main()
