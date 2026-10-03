import hashlib
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLACES = ROOT / 'src/data/places/places.generated.json'
MAP = (ROOT / 'src/components/RouteMap.astro').read_text(encoding='utf-8')
EXPECTED_SHA = '6ecfaa177860c2c59620e391b7c114577c9d2c3377c748b5984a2bc5c014e149'

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
        self.assertIn('Open in Google Maps', MAP)
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
