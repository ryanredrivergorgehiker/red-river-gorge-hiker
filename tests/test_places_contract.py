import hashlib
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLACES = ROOT / 'src/data/places/places.generated.json'
MAP = (ROOT / 'src/components/RouteMap.astro').read_text(encoding='utf-8')
EXPECTED_SHA = '68c97204370cdc05a704a8f3da8558305d8c2bd12e9d6e3753082812c0467219'

class PlacesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = PLACES.read_bytes()
        cls.data = json.loads(cls.raw)

    def test_exact_verification_cleared_snapshot(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), EXPECTED_SHA)
        self.assertEqual(self.data['metadata']['sourceRegisterId'], '1GcUKlJTy18qP4yGu4n1qhLzy3IkOM-U2M_2LJLYIW-4')
        self.assertEqual(self.data['metadata']['verificationState'], 'owner-uat-reconciled')

    def test_integrity_counts_and_canonical_identity(self):
        places = self.data['activePlaces']
        self.assertEqual(len(places), 30)
        self.assertEqual(len({p['placeId'] for p in places}), 30)
        self.assertEqual(sum(bool(p['aroundTheGorge']) for p in places), 24)
        self.assertEqual(sum(bool(p['hikerServices']) for p in places), 10)
        self.assertEqual(sum(bool(p['aroundTheGorge']) and bool(p['hikerServices']) for p in places), 4)
        self.assertEqual(sum(bool(p['rrghPresence']) for p in places), 3)
        self.assertEqual(sum(bool(p['mapPoiEligible']) for p in places), 30)
        self.assertEqual(len(self.data['excludedAndSuperseded']), 10)
        ex_by_id = {x['recordId']:x for x in self.data['excludedAndSuperseded']}
        self.assertIn('Current entity verified', ex_by_id['EX-007']['status'])
        self.assertIn('30 L&E Railroad Place', ex_by_id['EX-007']['governingNote'])
        self.assertTrue(all(isinstance(p['latitude'], (int,float)) and isinstance(p['longitude'], (int,float)) for p in places))
        by_id = {p['placeId']:p for p in places}
        self.assertEqual(by_id['PLC-021']['publicName'], 'The Brick at the Red River Gorge')
        self.assertEqual(by_id['PLC-026']['publicName'], 'Trails Liquor, Souvenir, & General Store')
        self.assertEqual(by_id['PLC-016']['publicName'], 'Southeast Mountain Guides')
        self.assertEqual(by_id['PLC-025']['publicName'], 'Park N Save')
        self.assertEqual((by_id['PLC-004']['latitude'], by_id['PLC-004']['longitude']), (37.7634, -83.6126))
        self.assertEqual((by_id['PLC-024']['latitude'], by_id['PLC-024']['longitude']), (37.7982345, -83.7046152))
        self.assertEqual(by_id['PLC-024']['hikerServiceTypes'], ['backcountry/overnight pass vendor', 'fuel', 'provisions'])
        self.assertEqual(by_id['PLC-024']['shortDescription'], 'Hiking-logistics stop for required backcountry/overnight pass acquisition, fuel, and provisions.')
        self.assertEqual((by_id['PLC-025']['latitude'], by_id['PLC-025']['longitude']), (37.7982107, -83.7026222))
        self.assertEqual((by_id['PLC-009']['latitude'], by_id['PLC-009']['longitude']), (37.7845241, -83.6914935))
        self.assertEqual((by_id['PLC-019']['latitude'], by_id['PLC-019']['longitude']), (37.781217, -83.689967))
        self.assertEqual((by_id['PLC-003']['latitude'], by_id['PLC-003']['longitude']), (by_id['PLC-023']['latitude'], by_id['PLC-023']['longitude']))
        self.assertEqual((by_id['PLC-012']['latitude'], by_id['PLC-012']['longitude']), (by_id['PLC-030']['latitude'], by_id['PLC-030']['longitude']))
        self.assertEqual(by_id['PLC-030']['publicName'], 'SUP Kentucky')
        self.assertTrue(all(p['googleMapsUrl'].startswith('https://www.google.com/maps/search/?api=1&query=') for p in places))
        self.assertNotIn('"29"', json.dumps(self.data['activePlaces']))
        self.assertTrue(by_id['PLC-010']['nearbyRrghPickEligible'])
        self.assertEqual(by_id['PLC-010']['nearbyRouteContext'], 'Motherlode area')

    def test_owner_supplied_exact_map_addresses(self):
        expected = {"PLC-001":"1890 Natural Bridge Rd, Slade, KY 40376","PLC-002":"4000 KY-11, Campton, KY 41301","PLC-003":"2135 Natural Bridge Rd, Slade, KY 40376","PLC-004":"8 KY-715, Pine Ridge, KY 41360","PLC-005":"2613 KY-11, Campton, KY 41301","PLC-006":"356 Jim Smith Rd, Campton, KY 41301","PLC-007":"1289 Natural Bridge Rd, Slade, KY 40376","PLC-008":"769 Natural Bridge Rd, Slade, KY 40376","PLC-009":"1255 Natural Bridge Rd, Slade, KY 40376","PLC-010":"2034 KY-11, Beattyville, KY 41311","PLC-011":"200 L&E Railroad Pl, Slade, KY 40376","PLC-012":"2478 Glencairn Rd, Rogers, KY 41365","PLC-013":"455 Cliffview Rd, Campton, KY 41301","PLC-014":"693 Natural Bridge Rd, Slade, KY 40376","PLC-015":"48 Muir Rd, Rogers, KY 41365","PLC-016":"1617 KY-11, Campton, KY 41301","PLC-017":"45 KY-715, Frenchburg, KY 40322","PLC-018":"888 Natural Bridge Rd, Slade, KY 40376","PLC-019":"607 Skylift Dr, Slade, KY 40376","PLC-020":"693 Natural Bridge Rd, Slade, KY 40376","PLC-021":"5412 KY-15 N, Pine Ridge, KY 41360","PLC-022":"1321 Natural Bridge Rd, Slade, KY 40376","PLC-023":"2135 Natural Bridge Rd, Slade, KY 40376","PLC-024":"12056 Campton Rd, Slade, KY 40376","PLC-025":"12187 Campton Rd, Slade, KY 40376","PLC-026":"940 Natural Bridge Rd, Slade, KY 40376","PLC-027":"1433 KY-36, Frenchburg, KY 40322","PLC-028":"6944 KY-52, Beattyville, KY 41311","PLC-029":"3451 Sky Bridge Rd, Stanton, KY 40380"}
        by_id = {p['placeId']:p for p in self.data['activePlaces']}
        for place_id, address in expected.items():
            self.assertEqual(by_id[place_id]['locationContext'], address)

    def test_one_poi_shared_selectors_and_presence_contract(self):
        self.assertIn('data-map-layer="around-the-gorge" checked', MAP)
        self.assertIn('data-map-layer="hiker-services" checked', MAP)
        self.assertIn('const placesLayerGroup = L.layerGroup().addTo(map)', MAP)
        self.assertIn('placeMarkerRecords.push({ place, marker })', MAP)
        self.assertIn('Boolean(place.aroundTheGorge) && checked(aroundPlacesLayerId)', MAP)
        self.assertIn('Boolean(place.hikerServices) && checked(hikerServicesLayerId)', MAP)
        self.assertIn("'rrgh-place-marker'", MAP)
        self.assertIn("'is-presence'", MAP)
        self.assertIn('rrgh-place-presence-badge', MAP)
        self.assertIn("label.textContent = 'RRGH Presence'", MAP)
        self.assertIn('route-layer-presence-example', MAP)
        self.assertIn('Current info on Google Maps', MAP)
        self.assertIn('Current info on Apple Maps', MAP)
        self.assertIn("new URL('https://maps.apple.com/place')", MAP)
        self.assertIn("appleMapsUrl.searchParams.set('coordinate', lat + ',' + lng)", MAP)
        self.assertIn("mapLink.target = '_blank'", MAP)
        self.assertIn("mapLink.rel = 'noopener noreferrer'", MAP)
        self.assertIn("mapIcon.className = 'route-map-service-icon'", MAP)
        self.assertNotIn("sourceLink.textContent = 'Official site'", MAP)
        self.assertNotIn('Check current source', MAP)
        self.assertNotIn('Around the Gorge and Hiker Services can classify the same place', MAP)
        self.assertNotIn("'partner'", MAP.lower())

    def test_preset_defaults_and_route_waypoint_separation(self):
        hiking = MAP.split("if (name === 'hiking')",1)[1].split("} else if (name === 'terrain')",1)[0]
        terrain = MAP.split("} else if (name === 'terrain')",1)[1].split("} else if (name === 'aerial')",1)[0]
        aerial = MAP.split("} else if (name === 'aerial')",1)[1].split("} else if (name === 'sunlight')",1)[0]
        sunlight = MAP.split("} else if (name === 'sunlight')",1)[1].split("syncAerialControlState()",1)[0]
        self.assertIn("setLayerControl(aroundPlacesLayerId, true)", hiking)
        self.assertIn("setLayerControl(hikerServicesLayerId, true)", hiking)
        for block in (terrain,aerial,sunlight):
            self.assertIn("setLayerControl(aroundPlacesLayerId, false)", block)
            self.assertIn("setLayerControl(hikerServicesLayerId, false)", block)
        self.assertIn("places: 465", MAP)
        self.assertIn("landmarks: 470", MAP)

if __name__ == '__main__':
    unittest.main()
