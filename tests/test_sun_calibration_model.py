"""Behavior checks for the terrain-first calibration, independent of map area."""
import sys
import unittest
from pathlib import Path

try:
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from sun_calibration import ridge_geometry, surface_classes, directional_pass, crest_fade, measured_horizon_surface, Rules
    HAS_GEOMETRY_LIBS = True
except ImportError:
    HAS_GEOMETRY_LIBS = False


@unittest.skipUnless(HAS_GEOMETRY_LIBS, 'Scientific dependencies run in the calibration workflow')
class SunCalibrationBehavior(unittest.TestCase):
    def test_crest_is_centered_and_planar_flank_is_not_a_ridge(self):
        y, x = np.mgrid[-200:202:2, -200:202:2]
        z = (220 + 45 * np.exp(-(x / 35) ** 2)).astype('float32')
        result = ridge_geometry(z, 2)
        rr, cc = np.nonzero(result['ridge'])
        self.assertGreater(len(rr), 50)
        self.assertLessEqual(np.max(np.abs(x[rr, cc])), 2)
        self.assertFalse(np.any(result['corridor'] & (np.abs(x) > 8)))
        plane = (220 + .2 * x + .1 * y).astype('float32')
        self.assertFalse(ridge_geometry(plane, 2)['ridge'].any())

    def test_valley_center_is_never_accepted_as_crest(self):
        _, x = np.mgrid[-200:202:2, -200:202:2]
        valley = (260 - 40 * np.exp(-(x / 35) ** 2)).astype('float32')
        result = ridge_geometry(valley, 2)
        self.assertFalse(result['ridge'][np.abs(x) < 10].any())

    def test_leaf_off_color_does_not_reclassify_tall_trees_as_open(self):
        ortho = np.full((4, 15, 15), 130, dtype='uint8')
        canopy = np.full((15, 15), 22, dtype='float32')
        count = np.full((15, 15), 10, dtype='uint16')
        classes, openness, _ = surface_classes(ortho, canopy, count, count)
        self.assertTrue((classes == 4).all())
        self.assertFalse(openness.any())

    def test_directions_are_independent_and_unknown_horizon_fails(self):
        z = np.full((1101, 1101), 60, dtype='float32')
        z[:, :552] = 100
        canopy = np.zeros_like(z)
        canopy[:, :548] = 20
        known = np.ones_like(z, dtype=bool)
        candidates = np.zeros_like(known); candidates[549:551, 550:552] = True
        openness = np.ones_like(z)
        rise = directional_pass(z, canopy, known, candidates, openness, 2, (90,))
        setting = directional_pass(z, canopy, known, candidates, openness, 2, (270,))
        self.assertGreater(rise[550, 550], 0)
        self.assertEqual(setting[550, 550], 0)
        known[:, 750:] = False
        self.assertFalse(directional_pass(z, canopy, known, candidates, openness, 2, (90,)).any())

    def test_fade_cannot_cross_a_hollow_or_cut_diagonal_corners(self):
        corridor = np.zeros((50, 100), dtype=bool)
        corridor[10:15, 5:90] = True
        corridor[25:30, 5:90] = True
        strength = np.ones(corridor.shape, dtype='float32')
        result = crest_fade(corridor, [(12, 10)], strength, strength, 2)
        self.assertGreater(result[12, 12], 0)
        self.assertFalse(result[25:30].any())
        self.assertFalse(result[~corridor].any())
        self.assertEqual(result[12, 80], 0)
        diagonal = np.eye(5, dtype=bool)
        result = crest_fade(diagonal, [(0, 0)], np.ones((5, 5)), np.ones((5, 5)), 2)
        self.assertFalse(result[1:].any())

    def test_flat_rock_top_is_not_limited_to_a_centerline_buffer(self):
        y, x = np.mgrid[-200:202:2, -200:202:2]
        z = np.where((np.abs(x) < 55) & (np.abs(y) < 90), 260., 220.).astype('float32')
        geometry = ridge_geometry(z, 2)
        self.assertTrue(geometry['corridor'][100, 120])
        self.assertGreater(geometry['distance'][100, 120], 6)

    def test_low_cover_alone_does_not_create_exposed_rock(self):
        ortho = np.full((4, 20, 20), 40, dtype='uint8')
        heights = np.zeros((20, 20), dtype='float32')
        count = np.full((20, 20), 10, dtype='uint16')
        classes, openness, _ = surface_classes(ortho, heights, count, count * 0)
        self.assertFalse(openness.any())
        ortho[:, 5:10, 5:10] = 140
        classes, openness, _ = surface_classes(ortho, heights, count, count * 0)
        self.assertTrue((classes[5:10, 5:10] == 1).all())
        self.assertTrue((openness[5:10, 5:10] > 0).all())

    def test_small_gap_uses_absolute_surface_and_large_gap_stays_unknown(self):
        z = np.full((25, 25), 100., dtype='float32')
        z[:, :10] = 200
        canopy = np.full_like(z, 20); canopy[:, :10] = 0
        known = np.ones_like(z, dtype=bool)
        z[12, 10] = 195; known[12, 10] = False
        known[:, 15:] = False
        top, valid = measured_horizon_surface(z, canopy, known, 2, Rules(canopy_gap_radius_m=4))
        self.assertEqual(top[12, 10], 200)
        self.assertEqual(top[12, 9], 200)  # measured open rock is unchanged
        self.assertFalse(valid[12, 24])
        self.assertTrue(np.isnan(top[12, 24]))

    def test_single_pixel_view_gap_is_not_a_usable_direction(self):
        z = np.full((151, 151), 50, dtype='float32'); z[:, :76] = 100
        known = np.ones_like(z, dtype=bool)
        candidate = np.zeros_like(known); candidate[75, 75] = True
        result = directional_pass(z, z * 0, known, candidate, z * 0 + 1, 2, (90,),
                                  Rules(horizon_distance_m=100))
        self.assertFalse(result.any())
