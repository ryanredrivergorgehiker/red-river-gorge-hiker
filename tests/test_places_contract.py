import hashlib
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLACES = ROOT / 'src/data/places/places.generated.json'
MAP = (ROOT / 'src/components/RouteMap.astro').read_text(encoding='utf-8')
EXPECTED_SHA = 'fb939c0d7325cf2bba1350799e8d2575d769f3248641fe4533f1758bd7455f77'

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
        self.assertEqual(by_id['PLC-024']['shortDescription'], 'Convenient stop for backcountry/overnight passes, fuel, food, drinks, and basic provisions.')
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


    def test_owner_revised_public_descriptions_and_presence_disclosures(self):
        expected = {
        "PLC-001": "Longtime Gorge-area pizza stop popular with hikers, climbers, and visitors.",
        "PLC-002": "Local restaurant serving burgers, sandwiches, salads, and other casual fare near the Gorge.",
        "PLC-003": "Sit-down restaurant at Natural Bridge State Resort Park, serving breakfast, lunch, and dinner.",
        "PLC-004": "Food, drinks, lodging, and limited visitor supplies near the eastern side of the Gorge.",
        "PLC-005": "Casual local restaurant and bar serving the Campton and Gorge area.",
        "PLC-006": "Local barbecue restaurant near the Gorge serving smoked meats and traditional sides.",
        "PLC-007": "Mexican restaurant in Slade serving tacos, burritos, fajitas, and other familiar favorites.",
        "PLC-008": "Coffee, breakfast, sandwiches, provisions, and backcountry/overnight pass sales in Slade.",
        "PLC-009": "Casual Slade restaurant serving hikers, climbers, and other Gorge visitors.",
        "PLC-010": "Beattyville-area pizza stop convenient to the Motherlode and nearby recreation areas.",
        "PLC-011": "Educational wildlife attraction specializing in reptiles, including venomous snake exhibits and programs.",
        "PLC-012": "Guided underground kayaking and boat tours through a flooded former limestone mine.",
        "PLC-013": "Guided zipline adventure overlooking the Gorge-area landscape.",
        "PLC-014": "Outdoor miniature-golf attraction in Slade; operating dates and hours may vary seasonally.",
        "PLC-015": "Privately managed nature preserve with extensive hiking and rock-climbing opportunities.",
        "PLC-016": "Guided rock climbing, rappelling, and via ferrata experiences near the Gorge. Formerly associated with the Torrent Falls Climbing Adventure operation.",
        "PLC-017": "Campground offering convenient access for paddling, camping, and overnight recreation in the Red River area.",
        "PLC-018": "Local shop offering Gorge-themed gifts, artwork, souvenirs, and locally connected merchandise.",
        "PLC-019": "Seasonal community market featuring local growers, makers, food producers, and other regional vendors.",
        "PLC-020": "Gorge-area gift and souvenir shop in Slade with locally themed merchandise.",
        "PLC-021": "Pine Ridge stop for ice cream, coffee, pottery, and locally made goods.",
        "PLC-022": "Groceries, snacks, ice cream, camping necessities, and commonly forgotten hiking supplies.",
        "PLC-023": "Lodge, restaurant, and visitor stop within Natural Bridge State Resort Park.",
        "PLC-024": "Convenient stop for backcountry/overnight passes, fuel, food, drinks, and basic provisions.",
        "PLC-025": "Convenience stop for backcountry/overnight passes, fuel, food, drinks, and basic provisions.",
        "PLC-026": "Gorge-area store offering backcountry/overnight passes along with drinks, snacks, souvenirs, and general supplies.",
        "PLC-027": "Frenchburg-area grocery and provisions stop useful for longer trips and resupply.",
        "PLC-028": "Beattyville-area grocery and provisions stop useful for longer trips and resupply.",
        "PLC-029": "Forest Service visitor center for maps, recreation information, trip planning, and Red River Gorge information.",
        "PLC-030": "Guided underground stand-up paddleboard and crystal-kayak tours in a flooded limestone mine."
}
        by_id = {p['placeId']:p for p in self.data['activePlaces']}
        self.assertEqual(set(expected), set(by_id))
        for place_id, description in expected.items():
            self.assertEqual(by_id[place_id]['shortDescription'], description)
        self.assertEqual(by_id['PLC-002']['relationshipDisclosure'], 'Red River Gorge Hiker photography is displayed and sold here. RRGH receives proceeds from photograph sales at this location. The business did not pay for inclusion on this map.')
        self.assertEqual(by_id['PLC-009']['relationshipDisclosure'], 'A Red River Gorge Hiker Double Rainbow photograph was donated for display here. The business did not pay for inclusion on this map.')
        self.assertEqual(by_id['PLC-018']['relationshipDisclosure'], 'Red River Gorge Hiker greeting cards are sold here. RRGH receives proceeds from greeting-card sales at this location. The business did not pay for inclusion on this map.')

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
        self.assertIn("className: 'rrgh-place-leaflet-popup'", MAP)
        self.assertIn("maxWidth: mobileMapActive() ? 232 : 360", MAP)
        self.assertIn("minWidth: mobileMapActive() ? 188 : 220", MAP)
        self.assertIn("keepInView: true", MAP)
        self.assertIn("autoPanPaddingTopLeft: [16, mobileMapActive() ? 118 : 72]", MAP)
        self.assertIn("autoPanPaddingBottomRight: [16, mobileMapActive() ? 84 : 56]", MAP)
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
        self.assertIn("recreation: 510", MAP)
        self.assertIn("routeStarts: 520", MAP)
        self.assertIn("places: 530", MAP)
        self.assertIn("landmarks: 540", MAP)
        self.assertIn("mapPoint: 560", MAP)

if __name__ == '__main__':
    unittest.main()
