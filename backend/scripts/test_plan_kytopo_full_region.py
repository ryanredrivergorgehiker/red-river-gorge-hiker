#!/usr/bin/env python3
"""Network-free exact-bbox Gorge KyTopo planning tests; no raster bytes."""
import unittest
from test_plan_kytopo_quad_seams import index
from plan_kytopo_full_region import plan, rectangle_union_covers


class RegionalKyTopoPlannerTests(unittest.TestCase):
    def test_exact_rectangle_union_rejects_unsampled_stripe(self):
        a = [0., 0., 1., 1.]
        self.assertTrue(rectangle_union_covers(a, [[0, 0, .5, 1], [.5, 0, 1, 1]]))
        self.assertFalse(rectangle_union_covers(a, [[0, 0, .499, 1], [.501, 0, 1, 1]]))
        self.assertFalse(rectangle_union_covers(a, [[0, 0, 1, .499], [0, .501, 1, 1]]))
        self.assertFalse(rectangle_union_covers(a, []))

    def test_full_region_has_deterministic_source_plan_but_never_pixel_approval(self):
        r = plan(index())
        self.assertEqual([r['zoom'] for r in r['levels']], list(range(10, 17)))
        self.assertEqual(r['totalCandidateTiles'], sum(v['expectedTiles'] for v in r['levels']))
        self.assertGreater(r['totalCandidateTiles'], 6000)
        self.assertGreater(r['totalMultiSourceCandidates'], 0)
        self.assertEqual(r['totalUncoveredBboxTiles'], 0)
        self.assertFalse(r['allActualPixelsCovered'])
        self.assertFalse(r['fullOfflineHikingPackComplete'])
        self.assertIsNone(r['downloadBytes'])
        self.assertTrue(all(not v['actualPixelCoverageVerified'] for v in r['plannedTiles']))
        self.assertEqual(r['plannedTiles'], plan(index())['plannedTiles'])

    def test_official_metadata_gap_is_reported_not_covered_up(self):
        doc = index()
        for quad in doc['quadrangles']:
            if quad['id'].startswith('N14'):
                quad['boundsWGS84'][1] += .01
        r = plan(doc, 15, 16)
        self.assertGreater(r['totalUncoveredBboxTiles'], 0)
        self.assertTrue(any(not t['sourceBboxUnionCoversClippedTile'] for t in r['plannedTiles']))
        self.assertFalse(r['allActualPixelsCovered'])

    def test_missing_or_nonofficial_original_fails_closed(self):
        doc = index()
        doc['quadrangles'][0]['officialOriginalCogURL'] = 'https://invalid.example/bogus.tif'
        with self.assertRaises(ValueError):
            plan(doc, 16, 16)
        doc = index()
        doc['quadrangles'].pop()
        with self.assertRaises(ValueError):
            plan(doc, 16, 16)
        with self.assertRaises(ValueError):
            plan(index(), 9, 16)


if __name__ == '__main__':
    unittest.main()
