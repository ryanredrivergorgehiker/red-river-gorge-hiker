"""Behavior checks for the terrain-first calibration, independent of map area."""
import sys
import unittest
from pathlib import Path

try:
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from sun_calibration import (ridge_geometry, surface_classes, directional_pass,
        measured_horizon_surface, absolute_point_surfaces, upper_lip_rock_support,
        generate, Rules)
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

    def test_curving_ridge_stays_connected_and_centered(self):
        from scipy.ndimage import label
        y, x = np.mgrid[-300:302:2, -300:302:2]
        center = 30 * np.sin(y / 120)
        z = (220 + 45 * np.exp(-((x - center) / 35) ** 2)).astype('float32')
        result = ridge_geometry(z, 2)
        ridge = result['ridge'] & (np.abs(y) < 180)
        rr, cc = np.nonzero(ridge)
        self.assertGreater(len(rr), 150)
        self.assertLess(np.percentile(np.abs(x[rr, cc] - center[rr, cc]), 95), 3)
        groups, _ = label(ridge, structure=np.ones((3, 3)))
        self.assertGreater(np.bincount(groups.ravel())[1:].max(), len(rr) * .95)

    def test_flat_upper_cliff_lip_is_standing_ground_but_face_is_not(self):
        y, x = np.mgrid[-200:202:2, -200:202:2]
        z = np.where((np.abs(x) < 55) & (np.abs(y) < 90), 260., 220.).astype('float32')
        geometry = ridge_geometry(z, 2)
        self.assertTrue(geometry['corridor'][100, 126])  # x=52, upper lip
        self.assertFalse(geometry['corridor'][100, 128])  # x=56, below cliff

    def test_same_open_rock_top_keeps_both_directions(self):
        z = np.full((401, 401), 60, dtype='float32')
        z[:, 176:225] = 100
        canopy = np.zeros_like(z)
        known = np.ones_like(z, dtype=bool)
        candidates = np.zeros_like(known); candidates[199:202, 199:202] = True
        openness = np.ones_like(z)
        rules = Rules(horizon_distance_m=300)
        rise = directional_pass(z, canopy, known, candidates, openness, 2, (90,), rules)
        setting = directional_pass(z, canopy, known, candidates, openness, 2, (270,), rules)
        self.assertTrue((rise[candidates] >= .6).all())
        self.assertTrue((setting[candidates] >= .6).all())
        canopy[:, 185:190] = 20
        blocked = directional_pass(z, canopy, known, candidates, openness, 2, (270,), rules)
        self.assertFalse(blocked.any())

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

    def test_cliff_cells_preserve_absolute_obstructions_and_measured_upper_ground(self):
        dem = np.array([[100., 70., 70., 100.]])
        ground_returns = np.array([[101., 99., -np.inf, -np.inf]])
        surface_returns = np.array([[102., 104., 90., -np.inf]])
        ground, cover = absolute_point_surfaces(dem, ground_returns, surface_returns)
        np.testing.assert_array_equal(ground, [[101., 99., 70., 100.]])
        np.testing.assert_array_equal(cover, [[1., 5., 20., 0.]])
        np.testing.assert_array_equal((ground + cover)[0, :3], surface_returns[0, :3])

    def test_rock_face_can_qualify_nearby_upper_lip_but_not_lower_or_distant_ground(self):
        z = np.full((20, 20), 90.)
        z[6, 10] = z[4, 10] = z[10, 0] = 110
        material = np.zeros_like(z, dtype=bool); material[10, 10] = True
        support = upper_lip_rock_support(z, material, 2)
        self.assertTrue(support[6, 10])  # eight meters away, above visible rock
        self.assertFalse(support[4, 10])  # twelve meters away
        self.assertFalse(support[9, 10])  # not an upper lip
        self.assertFalse(support[10, 0])  # no wrap across raster edge
        self.assertFalse(upper_lip_rock_support(z, material * False, 2).any())

    def test_descending_east_spur_has_sunrise_without_sunset_uphill_into_trees(self):
        z = np.full((151, 151), 60., dtype='float32')
        z[:, :76] = np.linspace(125, 100, 76)
        canopy = np.zeros_like(z); canopy[:, :73] = 20
        known = np.ones_like(z, dtype=bool)
        candidates = np.zeros_like(known); candidates[74:77, 74:76] = True
        rules = Rules(horizon_distance_m=100)
        rise = directional_pass(z, canopy, known, candidates, z * 0 + 1, 2, (90,), rules)
        setting = directional_pass(z, canopy, known, candidates, z * 0 + 1, 2, (270,), rules)
        self.assertTrue(rise[candidates].all())
        self.assertFalse(setting.any())

    def test_narrow_view_on_usable_rock_footprint_is_retained_at_its_actual_cell(self):
        z = np.full((151, 151), 60., dtype='float32'); z[:, :76] = 100
        canopy = np.zeros_like(z); canopy[:, 76] = 60
        canopy[75, 76] = 0  # one clear eye-level opening on a larger standing top
        known = np.ones_like(z, dtype=bool)
        candidates = np.zeros_like(known); candidates[73:78, 74:76] = True
        result = directional_pass(z, canopy, known, candidates, z * 0 + 1, 2, (90,),
                                  Rules(horizon_distance_m=100))
        self.assertGreater(result[75, 75], 0)
        self.assertEqual(result[74, 75], 0)
        self.assertEqual(result[76, 75], 0)

    def test_northwest_opening_does_not_pass_blocked_west(self):
        z = np.full((151, 151), 60., dtype='float32'); z[70:81, 70:81] = 100
        canopy = np.zeros_like(z); canopy[72:79, 55:65] = 70
        known = np.ones_like(z, dtype=bool)
        candidates = np.zeros_like(known); candidates[74:77, 74:77] = True
        rules = Rules(horizon_distance_m=100)
        west = directional_pass(z, canopy, known, candidates, z * 0 + 1, 2, (270,), rules)
        northwest = directional_pass(z, canopy, known, candidates, z * 0 + 1, 2, (302,), rules)
        self.assertFalse(west.any())
        self.assertTrue(northwest.any())

    def test_composite_never_spreads_past_each_cells_own_visibility(self):
        y, x = np.mgrid[-300:302:2, -300:302:2]
        z = np.where((np.abs(x) < 55) & (np.abs(y) < 100), 260., 220.).astype('float32')
        ortho = np.full((4, *z.shape), 130, dtype='uint8')
        canopy = np.zeros_like(z); canopy[(x < -50) & (y > 0)] = 60
        count = np.full(z.shape, 10, dtype='uint16')
        result = generate(z, ortho, canopy, count, count * 0, 2, Rules(horizon_distance_m=150))
        rise, setting = result['sunrise'], result['sunset']
        self.assertTrue((rise > 0).any())
        self.assertTrue((setting > 0).any())
        self.assertTrue(((rise > 0) & (setting > 0)).any())
        for direction in ['sunrise', 'sunset']:
            np.testing.assert_array_equal(result[direction], result[direction + '_pass'])
            self.assertGreater(np.count_nonzero(result[direction]), len(result[direction + '_seeds']))
            self.assertFalse(result[direction][~result['candidates']].any())

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

    def test_isolated_candidate_pixel_is_not_a_usable_standing_footprint(self):
        z = np.full((151, 151), 50, dtype='float32'); z[:, :76] = 100
        known = np.ones_like(z, dtype=bool)
        candidate = np.zeros_like(known); candidate[75, 75] = True
        result = directional_pass(z, z * 0, known, candidate, z * 0 + 1, 2, (90,),
                                  Rules(horizon_distance_m=100))
        self.assertFalse(result.any())
