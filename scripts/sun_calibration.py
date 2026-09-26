"""Terrain-first photographic-potential calibration, with no network I/O.

Ridge locations depend only on bare-earth elevation. Vegetation qualifies a
standing candidate and its viewing sector; it cannot move the terrain geometry.
All distances below are ground meters, not Web Mercator map meters.
"""
from dataclasses import dataclass
import heapq
import math

import numpy as np
from scipy.ndimage import (
    binary_closing, convolve, distance_transform_edt, gaussian_filter, label,
    map_coordinates, maximum_filter, minimum_filter, uniform_filter,
)
from skimage.morphology import skeletonize

VERSION = 11


@dataclass(frozen=True)
class Rules:
    ridge_scale_m: float = 6.0
    corridor_radius_m: float = 6.0
    corridor_max_below_crest_m: float = 1.8
    max_standing_slope_deg: float = 25.0
    minimum_segment_m: float = 24.0
    maximum_fade_m: float = 70.0
    observer_height_m: float = 1.6
    horizon_limit_deg: float = 5.0
    horizon_distance_m: float = 1000.0


DEFAULT_RULES = Rules()


def remove_short_components(mask, min_pixels):
    groups, _ = label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    counts = np.bincount(groups.ravel())
    keep = counts >= min_pixels
    keep[0] = False
    return keep[groups]


def ridge_geometry(elevation, cell_m, rules=DEFAULT_RULES):
    """Locate transverse elevation maxima, then bound a separate crest corridor.

    A watershed seeded only at local stream minima misses continuous tributary
    channels and their intervening ridge fingers. Here the Hessian gives the
    cross-ridge direction, and the first derivative must cross zero within the
    pixel: curvature alone is explicitly insufficient to accept a ridge side.
    Derivatives of the smoothed surface use finite differences, avoiding the
    nonzero constant-surface residual of a truncated Gaussian second derivative.
    """
    z = np.asarray(elevation, dtype=np.float32)
    smooth = gaussian_filter(z, rules.ridge_scale_m / cell_m)
    gy, gx = np.gradient(smooth, cell_m)
    hxy, hxx = np.gradient(gx, cell_m)
    hyy, _ = np.gradient(gy, cell_m)
    eigen = (hxx + hyy - np.hypot(hxx - hyy, 2 * hxy)) / 2
    normal_angle = .5 * np.arctan2(2 * hxy, hxx - hyy) + np.pi / 2
    nx, ny = np.cos(normal_angle), np.sin(normal_angle)
    offset = -(gx * nx + gy * ny) / np.minimum(eigen, -1e-6)
    transverse_maximum = (
        (np.abs(offset * nx) < cell_m * .65)
        & (np.abs(offset * ny) < cell_m * .65)
        & (eigen < -.006)
    )
    rows, cols = np.indices(z.shape, dtype=np.float32)
    bilateral = np.zeros(z.shape, dtype=bool)
    for distance_m, minimum_drop_m in ((24, 1), (48, 3), (80, 8)):
        positive = map_coordinates(smooth, [rows + ny * distance_m / cell_m,
                                           cols + nx * distance_m / cell_m], order=1, mode='nearest')
        negative = map_coordinates(smooth, [rows - ny * distance_m / cell_m,
                                           cols - nx * distance_m / cell_m], order=1, mode='nearest')
        bilateral |= np.minimum(smooth - positive, smooth - negative) > minimum_drop_m

    radius = max(3, round(250 / cell_m))
    local_low = minimum_filter(z, size=radius * 2 + 1)
    local_high = maximum_filter(z, size=radius * 2 + 1)
    relative_height = (z - local_low) / np.maximum(local_high - local_low, 1)
    broad_tpi = z - gaussian_filter(z, 120 / cell_m)
    upper_landform = (broad_tpi > 1) & (relative_height > .35)
    ridge = transverse_maximum & bilateral & upper_landform
    ridge = skeletonize(binary_closing(ridge, structure=np.ones((3, 3))))
    ridge = remove_short_components(ridge, math.ceil(rules.minimum_segment_m / cell_m))
    # Numerical edge neighborhoods lack symmetric evidence. Never display them.
    border = math.ceil(85 / cell_m)
    ridge[:border] = ridge[-border:] = False
    ridge[:, :border] = ridge[:, -border:] = False

    dy, dx = np.gradient(gaussian_filter(z, .7), cell_m)
    slope = np.degrees(np.arctan(np.hypot(dx, dy)))
    distance, nearest = distance_transform_edt(~ridge, sampling=cell_m, return_indices=True)
    below_crest = z[nearest[0], nearest[1]] - z
    corridor = (
        (distance <= rules.corridor_radius_m)
        & (below_crest <= rules.corridor_max_below_crest_m)
        & (slope <= rules.max_standing_slope_deg)
        & upper_landform
    )
    corridor = remove_short_components(corridor, 4)
    return {'ridge': ridge, 'corridor': corridor, 'slope': slope,
            'distance': distance, 'below_crest': below_crest}


def surface_classes(ortho, canopy_height, return_count, elevated_count):
    """Separate measured tall cover from low cover in leaf-off aerial imagery.

    Class 1 is low vegetation/exposed-surface evidence, not a promise of bare
    rock. Class 2 is a green clearing; 3 partial cover; 4 tall/dense cover.
    Class 0 is unknown. No percentile quota forces forest into an open class.
    """
    red, green, blue, nir = np.asarray(ortho, dtype=np.float32)
    ndvi = (nir - red) / np.maximum(nir + red, 1)
    total = uniform_filter(return_count.astype(np.float32), 3)
    elevated = uniform_filter(elevated_count.astype(np.float32), 3)
    fraction = elevated / np.maximum(total, .01)
    known = (return_count > 0) & ((red + green + blue) > 15)
    # Do not dilate neighboring crowns across an exposed rim. The point-cloud
    # raster already records height in each cell; a 3x3 maximum would invent a
    # six-meter-wide obstruction in a physically open viewing sector.
    local_height = canopy_height
    low_cover = known & (canopy_height <= 3) & (fraction < .40)
    classes = np.zeros(canopy_height.shape, dtype=np.uint8)
    classes[known] = 4
    classes[known & ((canopy_height < 8) | (fraction < .5))] = 3
    classes[low_cover & (ndvi >= .28)] = 2
    classes[low_cover & (ndvi < .28)] = 1
    openness = np.clip((.55 - fraction) / .45, 0, 1)
    openness *= np.clip((5 - canopy_height) / 4, 0, 1)
    openness[~known] = 0
    return classes, openness, local_height


def geometric_overlooks(z, corridor, cell_m):
    """Require a cliff/rim break before any canopy or sun evaluation."""
    rr, cc = np.nonzero(corridor)
    best = np.zeros(len(rr), dtype=np.float32)
    for az in range(0, 360, 30):
        angle = math.radians(az)
        for distance in (16, 24, 36):
            r = rr - math.cos(angle) * distance / cell_m
            c = cc + math.sin(angle) * distance / cell_m
            target = map_coordinates(z, [r, c], order=1, mode='constant', cval=np.nan)
            drop = z[rr, cc] - target
            best = np.maximum(best, np.nan_to_num(drop, nan=0))
    strength = np.zeros(z.shape, np.float32)
    strength[rr, cc] = np.clip((best - 10) / 25, 0, 1)
    return strength


def directional_pass(z, canopy, known, candidates, open_ground, cell_m,
                     azimuths, rules=DEFAULT_RULES):
    """Test seasonal viewing fans independently, including near-field trees.

    A direction qualifies only when 3/5 fan rays have a complete measured
    1 km horizon, a near-field terrain fall-away, and no obstruction above 5°.
    The observer is 1.6 m above the accepted standing cell. Unknown rays fail.
    """
    rr, cc = np.nonzero(candidates)
    result = np.zeros(z.shape, np.float32)
    if not len(rr):
        return result
    eye = z[rr, cc] + rules.observer_height_m
    surface = z + canopy
    coverage_grid = known.astype(np.float32)
    best = np.zeros(len(rr), np.float32)
    # Dense sampling avoids skipping a narrow intervening ridge or tree belt.
    distances = np.arange(4, rules.horizon_distance_m + 1, 4)
    for azimuth in azimuths:
        ray_scores = []
        for fan_offset in (-10, -5, 0, 5, 10):
            angle = math.radians(azimuth + fan_offset)
            peak_angle = np.full(len(rr), -90, np.float32)
            near_drop = np.zeros(len(rr), np.float32)
            observed = np.ones(len(rr), bool)
            for distance in distances:
                r = rr - math.cos(angle) * distance / cell_m
                c = cc + math.sin(angle) * distance / cell_m
                terrain = map_coordinates(z, [r, c], order=1, mode='constant', cval=np.nan)
                top = map_coordinates(surface, [r, c], order=1, mode='constant', cval=np.nan)
                coverage = map_coordinates(coverage_grid, [r, c], order=0, mode='constant', cval=0)
                observed &= np.isfinite(top) & (coverage > 0)
                angle_deg = np.degrees(np.arctan2(top - eye, distance))
                peak_angle = np.maximum(peak_angle, np.nan_to_num(angle_deg, nan=90))
                if distance <= 36:
                    near_drop = np.maximum(near_drop, np.nan_to_num(z[rr, cc] - terrain, nan=0))
            passes = observed & (peak_angle <= rules.horizon_limit_deg) & (near_drop >= 10)
            score = np.clip((near_drop - 8) / 22, 0, 1)
            score *= np.clip((rules.horizon_limit_deg + 3 - peak_angle) / 8, 0, 1)
            ray_scores.append(np.where(passes, score, 0))
        # Third-best of five rays: a real sector, not a single gap in foliage.
        best = np.maximum(best, np.sort(ray_scores, axis=0)[2])
    result[rr, cc] = best * open_ground[rr, cc]
    return result


def select_seeds(strength, cell_m, spacing_m=45):
    local = maximum_filter(strength, size=max(3, round(12 / cell_m) * 2 + 1))
    rr, cc = np.nonzero((strength >= .18) & (strength == local))
    order = sorted(zip(rr.tolist(), cc.tolist()), key=lambda p: (-float(strength[p]), p))
    chosen = []
    separation_sq = (spacing_m / cell_m) ** 2
    for r, c in order:
        if all((r - y) ** 2 + (c - x) ** 2 >= separation_sq for y, x in chosen):
            chosen.append((r, c))
    return chosen


def crest_fade(corridor, seeds, strength, open_ground, cell_m, rules=DEFAULT_RULES):
    """Fade along connected standable crest cells with no radial blur.

    Every colored pixel is reached by an 8-neighbor walk from a qualifying
    viewpoint. Tall cover shortens the path. Diagonal corner cutting is banned.
    """
    rows, cols = corridor.shape
    result = np.zeros(corridor.shape, np.float32)
    for sr, sc in seeds:
        queue = [(0., sr, sc)]
        distances = {(sr, sc): 0.}
        seed_strength = float(strength[sr, sc])
        while queue:
            distance, r, c = heapq.heappop(queue)
            if distance != distances[(r, c)] or distance > rules.maximum_fade_m:
                continue
            value = seed_strength * (1 - distance / rules.maximum_fade_m) ** 1.5
            result[r, c] = max(result[r, c], value)
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols and corridor[nr, nc]):
                    continue
                if dr and dc and not (corridor[r, nc] and corridor[nr, c]):
                    continue
                cost = cell_m * math.hypot(dr, dc) * (1 + 1.5 * (1 - float(open_ground[nr, nc])))
                next_distance = distance + cost
                if next_distance < distances.get((nr, nc), float('inf')) and next_distance <= rules.maximum_fade_m:
                    distances[nr, nc] = next_distance
                    heapq.heappush(queue, (next_distance, nr, nc))
    return result


def generate(elevation, ortho, canopy_height, return_count, elevated_count,
             cell_m, rules=DEFAULT_RULES):
    geometry = ridge_geometry(elevation, cell_m, rules)
    overlooks = geometric_overlooks(elevation, geometry['corridor'], cell_m)
    classes, openness, canopy_surface = surface_classes(ortho, canopy_height, return_count, elevated_count)
    candidates = (overlooks > 0) & (openness >= .2)
    known = return_count > 0
    sunrise = directional_pass(elevation, canopy_surface, known, candidates, openness, cell_m, (58, 90, 122), rules)
    sunset = directional_pass(elevation, canopy_surface, known, candidates, openness, cell_m, (238, 270, 302), rules)
    # Both directions must qualify independently; do not manufacture the weaker
    # direction from a shared elevation or aspect score.
    sunrise *= (.6 + .4 * overlooks)
    sunset *= (.6 + .4 * overlooks)
    rise_seeds = select_seeds(sunrise, cell_m)
    set_seeds = select_seeds(sunset, cell_m)
    return {**geometry, 'overlooks': overlooks, 'classes': classes, 'openness': openness,
            'sunrise_pass': sunrise, 'sunset_pass': sunset,
            'sunrise': crest_fade(geometry['corridor'], rise_seeds, sunrise, openness, cell_m, rules),
            'sunset': crest_fade(geometry['corridor'], set_seeds, sunset, openness, cell_m, rules),
            'sunrise_seeds': rise_seeds, 'sunset_seeds': set_seeds}
