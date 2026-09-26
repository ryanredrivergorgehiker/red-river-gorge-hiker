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

VERSION = 12


@dataclass(frozen=True)
class Rules:
    ridge_scale_m: float = 6.0
    corridor_radius_m: float = 6.0
    corridor_max_below_crest_m: float = 1.8
    max_standing_slope_deg: float = 25.0
    minimum_segment_m: float = 24.0
    maximum_fade_m: float = 70.0
    observer_height_m: float = 1.6
    horizon_limit_deg: float = 3.0
    horizon_distance_m: float = 1000.0
    canopy_gap_radius_m: float = 12.0
    minimum_view_area_m2: float = 16.0
    minimum_sector_degrees: float = 30.0
    minimum_seed_strength: float = 0.6
    top_neighborhood_m: float = 24.0
    top_relief_m: float = 4.0


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
    narrow_crest = remove_short_components(corridor, 4)
    # A ridge centerline is a diagnostic, not the boundary of a rock platform.
    # Include locally high, gentle tops beside the spine; the subsequent aerial
    # test must independently establish an exposed surface before seeding color.
    top_radius = math.ceil(rules.top_neighborhood_m / cell_m)
    local_top = maximum_filter(z, size=2 * top_radius + 1)
    standing_top = (upper_landform & (slope <= rules.max_standing_slope_deg)
                    & (local_top - z <= rules.top_relief_m))
    corridor = remove_short_components(narrow_crest | standing_top, 4)
    return {'ridge': ridge, 'corridor': corridor, 'slope': slope,
            'distance': distance, 'below_crest': below_crest, 'narrow_crest': narrow_crest}


def surface_classes(ortho, canopy_height, return_count, elevated_count, cell_m=2.):
    """Require connected rock-like aerial material, not simply low vegetation.

    A gray leaf-off forest opening is not an exposed overlook. The aerial test
    requires low NDVI, adequate brightness, modest chroma and >=24 m² of connected
    material; measured local height must also be below four meters. Classes are
    unknown, exposed-surface evidence, green clearing, partial/other, tall cover.
    """
    red, green, blue, nir = np.asarray(ortho, dtype=np.float32)
    ndvi = (nir - red) / np.maximum(nir + red, 1)
    brightness = (red + green + blue) / 3
    chroma = (np.maximum.reduce([red, green, blue]) - np.minimum.reduce([red, green, blue])) / np.maximum(brightness, 1)
    total = uniform_filter(return_count.astype(np.float32), 3)
    fraction = uniform_filter(elevated_count.astype(np.float32), 3) / np.maximum(total, .01)
    known = (return_count > 0) & (brightness > 5)
    material = (ndvi < .15) & (brightness >= 90) & (chroma < .4)
    material = remove_short_components(material, math.ceil(24 / cell_m ** 2))
    exposed = known & material & (canopy_height < 4)
    low_cover = known & (canopy_height <= 3) & (fraction < .4)
    classes = np.zeros(canopy_height.shape, dtype=np.uint8)
    classes[known] = 4
    classes[known & ((canopy_height < 8) | (fraction < .5))] = 3
    classes[low_cover & (ndvi >= .28)] = 2
    classes[exposed] = 1
    openness = np.where(exposed, np.clip((5 - canopy_height) / 4, .25, 1), 0).astype(np.float32)
    return classes, openness, canopy_height


def measured_horizon_surface(z, canopy, known, cell_m, rules=DEFAULT_RULES):
    """Bounded gap fill of ABSOLUTE measured elevations, never assumed bare earth.

    Sparse returns and water leave holes. At each hole use the maximum measured
    surface in the smallest surrounding pixel window that has evidence, up to
    12 m in either grid direction. Never expand trees into measured open cells,
    never propagate an interpolated value, and keep larger gaps unknown.
    Filling canopy *height* would invent tall obstructions on adjacent rock;
    filling absolute elevation preserves the cliff fall-away.
    """
    measured = np.where(known, z + canopy, -np.inf)
    surface = measured.copy()
    valid = known.copy()
    for radius in range(1, math.ceil(rules.canopy_gap_radius_m / cell_m) + 1):
        nearby = maximum_filter(measured, size=2 * radius + 1, mode='constant', cval=-np.inf)
        fill = ~valid & np.isfinite(nearby)
        surface[fill] = nearby[fill]
        valid[fill] = True
    surface[~valid] = np.nan
    return surface, valid


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
                     azimuths, rules=DEFAULT_RULES, horizon=None):
    """Require a broad low-obstruction sector and a usable connected footprint.

    Evaluate every 5° around each representative seasonal azimuth. A 30° window must pass
    six of seven rays: <=3° measured horizon and >=10 m fall-away within 36 m.
    The direction must also occupy at least 16 m² of adjacent candidate ground.
    The opposite direction is evaluated independently with exactly these rules.
    """
    rr, cc = np.nonzero(candidates)
    result = np.zeros(z.shape, np.float32)
    if not len(rr):
        return result
    surface, covered = horizon if horizon is not None else measured_horizon_surface(z, canopy, known, cell_m, rules)
    coverage_grid = covered.astype(np.uint8)
    distances = np.arange(4, rules.horizon_distance_m + 1, 4, dtype=np.float32)
    width = round(rules.minimum_sector_degrees / 5) + 1
    offsets = np.linspace(-rules.minimum_sector_degrees / 2,
                          rules.minimum_sector_degrees / 2, width)
    angles = [azimuth + offset for azimuth in azimuths for offset in offsets]
    # Vectorize each ray, in bounded batches, rather than resampling full grids
    # once for every individual distance. This retains four-meter sampling.
    for start in range(0, len(rr), 2048):
        rows, cols = rr[start:start + 2048], cc[start:start + 2048]
        eye = z[rows, cols, None] + rules.observer_height_m
        scores = []
        for azimuth in angles:
            angle = math.radians(azimuth)
            r = rows[:, None] - math.cos(angle) * distances / cell_m
            c = cols[:, None] + math.sin(angle) * distances / cell_m
            terrain = map_coordinates(z, [r, c], order=1, mode='constant', cval=np.nan)
            top = map_coordinates(surface, [r, c], order=1, mode='constant', cval=np.nan)
            coverage = map_coordinates(coverage_grid, [r, c], order=0, mode='constant', cval=0)
            observed = np.isfinite(top).all(axis=1) & (coverage > 0).all(axis=1)
            peak = np.nan_to_num(np.max(np.degrees(np.arctan2(top - eye, distances)), axis=1), nan=90)
            near_drop = np.nan_to_num(np.max(z[rows, cols, None] - terrain[:, distances <= 36], axis=1), nan=0)
            passed = observed & (peak <= rules.horizon_limit_deg) & (near_drop >= 10)
            score = np.clip((near_drop - 8) / 22, 0, 1)
            score *= np.clip((rules.horizon_limit_deg + 3 - peak) / 6, 0, 1)
            scores.append(np.where(passed, score, 0))
        scores = np.asarray(scores)
        sectors = []
        for index in range(0, len(angles), width):
            # The actual seasonal solar azimuth must pass too; clear neighbors
            # cannot turn an obstructed center ray into a sun-facing viewpoint.
            sector = np.sort(scores[index:index + width], axis=0)[1]
            sector[scores[index + width // 2] == 0] = 0
            sectors.append(sector)
        best = np.max(sectors, axis=0)
        result[rows, cols] = best * open_ground[rows, cols]
    usable = remove_short_components(result >= .18, math.ceil(rules.minimum_view_area_m2 / cell_m ** 2))
    result[~usable] = 0
    return result


def select_seeds(strength, cell_m, spacing_m=45, minimum_strength=.6):
    local = maximum_filter(strength, size=max(3, round(12 / cell_m) * 2 + 1))
    rr, cc = np.nonzero((strength >= minimum_strength) & (strength == local))
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
    classes, openness, canopy_surface = surface_classes(ortho, canopy_height, return_count, elevated_count, cell_m)
    candidates = (overlooks > 0) & (openness >= .2)
    known = return_count > 0
    horizon = measured_horizon_surface(elevation, canopy_surface, known, cell_m, rules)
    sunrise = directional_pass(elevation, canopy_surface, known, candidates, openness, cell_m, (58, 90, 122), rules, horizon)
    sunset = directional_pass(elevation, canopy_surface, known, candidates, openness, cell_m, (238, 270, 302), rules, horizon)
    # Both directions must qualify independently; do not manufacture the weaker
    # direction from a shared elevation or aspect score.
    sunrise *= (.6 + .4 * overlooks)
    sunset *= (.6 + .4 * overlooks)
    fade_ground = geometry['corridor'] & (geometry['narrow_crest'] | (classes == 1))
    rise_seeds = select_seeds(sunrise, cell_m, minimum_strength=rules.minimum_seed_strength)
    set_seeds = select_seeds(sunset, cell_m, minimum_strength=rules.minimum_seed_strength)
    return {**geometry, 'overlooks': overlooks, 'classes': classes, 'openness': openness,
            'sunrise_pass': sunrise, 'sunset_pass': sunset,
            'sunrise': crest_fade(fade_ground, rise_seeds, sunrise, openness, cell_m, rules),
            'sunset': crest_fade(fade_ground, set_seeds, sunset, openness, cell_m, rules),
            'sunrise_seeds': rise_seeds, 'sunset_seeds': set_seeds}
