import hashlib
import pathlib
import unittest
import xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(p): return (ROOT/p).read_text(encoding='utf-8')

class RoutesTracksContract(unittest.TestCase):
    def test_approved_artifact_hashes_and_hygiene(self):
        gpx=(ROOT/'public/downloads/routes/skybridge-arch.gpx').read_bytes()
        geo=(ROOT/'public/data/routes/skybridge-arch.geojson').read_bytes()
        self.assertEqual(hashlib.sha256(gpx).hexdigest(),'2469c85ebaddd3e701ba6dc8eea3664d90a0667dcd86f2aab43ae1445986830d')
        self.assertEqual(hashlib.sha256(geo).hexdigest(),'123fdb57e1142299f86c714367cc466b70f18fa90cfbaabb92b0d9ced157dc66')
        root=ET.fromstring(gpx)
        ns={'g':'http://www.topografix.com/GPX/1/1'}
        self.assertEqual(len(root.findall('.//g:trkpt',ns)),100)
        self.assertEqual(len(root.findall('.//g:wpt',ns)),2)
        self.assertFalse(root.findall('.//g:time',ns))
        self.assertFalse(root.findall('.//g:ele',ns))
        self.assertEqual([w.find('g:name',ns).text for w in root.findall('.//g:wpt',ns)],['Skybridge Arch','Turnaround Overlook'])

    def test_public_route_contract_and_private_boundary(self):
        route=read(pathlib.Path('src/data/routes/skybridge-arch.md'))
        self.assertIn('RTE-0001',route)
        self.assertIn('Approved — Publication Ready',route)
        self.assertIn('distanceMi: 0.784',route)
        self.assertIn('WP-0001',route)
        self.assertIn('WP-0002',route)
        forbidden=['1w0Uq5LPJxmVKEQCqJ6SIvdSGOEAnP_lM','1PaL0N8YX811a7q0n5X7rmvT4DYVil6HK','1UcAecDg8fHKdb1vnEeV7n0I9nRTK-X0m','1V8ycSPIPLbHme73yxjiPAD67x6Opqqvj']
        combined='\n'.join(read(p.relative_to(ROOT)) for root in [ROOT/'src/data/routes',ROOT/'public/data/routes',ROOT/'public/downloads/routes'] for p in root.rglob('*') if p.is_file())
        for token in forbidden: self.assertNotIn(token,combined)
        self.assertNotIn('eagle nest',read(pathlib.Path('public/data/routes/skybridge-arch.geojson')).lower())

    def test_routes_pages_sources_legal_and_explore_integration(self):
        for p in ['src/pages/routes/index.astro','src/pages/routes/[slug].astro','src/pages/routes/map.astro','src/pages/guides/kentucky-lidar.astro','src/components/routes/RouteMap.astro','src/components/routes/RouteLegalNotice.astro']:
            self.assertTrue((ROOT/p).exists(),p)
        explore=read(pathlib.Path('src/data/explore.ts'))
        self.assertIn("RRGH Hikes & Routes",explore)
        self.assertIn("RRGH Interactive Map",explore)
        self.assertIn("Kentucky LiDAR Guide",explore)
        terms=read(pathlib.Path('src/pages/copyright-and-terms.astro'))
        self.assertIn('Routes, Maps, GPS Tracks, and Location Information',terms)
        self.assertIn('GPX Download License',terms)
        self.assertNotIn('not a trail guide, navigation service',terms)
        privacy=read(pathlib.Path('src/pages/privacy.astro'))
        self.assertIn('Interactive Maps and Map-Data Services',privacy)
        notice=read(pathlib.Path('src/components/routes/RouteLegalNotice.astro'))
        self.assertIn('Route information is not a safety or access guarantee.',notice)
        self.assertIn('OFF-TRAIL / ADVANCED ROUTE',notice)

    def test_source_registry_and_parcel_hold(self):
        layers=read(pathlib.Path('src/data/map/layers.ts'))
        self.assertIn('Ky_KyTopo_Map_Series_WGS84WM',layers)
        self.assertIn('Ky_MultiDirectional_Hillshade_WGS84WM',layers)
        self.assertIn('Ky_Imagery_Phase3_3IN_WGS84WM',layers)
        self.assertIn('USGSTopo',layers)
        self.assertIn('epqs.nationalmap.gov/v1/json',layers)
        parcel=layers[layers.index("id: 'parcel-private-property'"):]
        self.assertIn('enabled: false',parcel)
        self.assertIn('BLOCKED.',parcel)

    def test_map_filters_and_deliberate_wheel_zoom(self):
        component=read(pathlib.Path('src/components/routes/RouteMap.astro'))
        script=read(pathlib.Path('src/scripts/route-map.js'))
        presets=read(pathlib.Path('src/data/map/presets.ts'))
        for token in ['Simple','Terrain','Route Planning','Land & Access','All Layers']:
            self.assertIn(token,presets)
        self.assertIn('data-trail-filter="official"',component)
        self.assertIn("scrollWheelZoom: config.mode === 'full'",script)
        self.assertIn("event.key === 'Escape'",script)
        self.assertIn('waypointMinZoom',script)

if __name__=='__main__':
    unittest.main()
