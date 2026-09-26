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
    binary_dilation, find_objects,
)
from skimage.morphology import skeletonize
from skimage.graph import route_through_array

VERSION = 13


@dataclass(frozen=True)
class Rules:
    ridge_scale_m: float = 2.0
    corridor_radius_m: float = 6.0
    corridor_max_below_crest_m: float = 1.8
    max_standing_slope_deg: float = 25.0
    minimum_segment_m: float = 40.0
    maximum_fade_m: float = 70.0
    observer_height_m: float = 1.6
    horizon_limit_deg: float = 3.0
    horizon_distance_m: float = 1000.0
    canopy_gap_radius_m: float = 12.0
    minimum_view_area_m2: float = 16.0
    minimum_sector_degrees: float = 30.0
    minimum_seed_strength: float = 0.6
    top_neighborhood_m: float = 24.0
    near_view_distance_m: float = 80.0


DEFAULT_RULES = Rules()


def remove_short_components(mask, min_pixels):
    groups, _ = label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    counts = np.bincount(groups.ravel())
    keep = counts >= min_pixels
    keep[0] = False
    return keep[groups]


def prune_ridge_branches(sk, minimum_length_m, cell_m):
    """Remove short terminal twigs, preserving endpoints of longer ridge limbs."""
    sk = sk.copy()
    limit = minimum_length_m / cell_m
    for _ in range(5):
        degree = convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8)) - sk
        remove = set()
        for root in zip(*np.nonzero(sk & (degree == 1))):
            path, previous, current, length = [root], None, root, 0
            while length <= limit:
                neighbors = [
                    (current[0] + dr, current[1] + dc)
                    for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                    if (dr or dc)
                    and 0 <= current[0] + dr < sk.shape[0]
                    and 0 <= current[1] + dc < sk.shape[1]
                    and sk[current[0] + dr, current[1] + dc]
                    and (current[0] + dr, current[1] + dc) != previous
                ]
                if len(neighbors) != 1:
                    break
                next_pixel = neighbors[0]
                length += np.hypot(next_pixel[0] - current[0], next_pixel[1] - current[1])
                previous, current = current, next_pixel
                if degree[current] >= 3:
                    break
                path.append(current)
            if length <= limit and degree[current] >= 3:
                remove.update(path)
        if not remove:
            break
        rr, cc = np.array(list(remove)).T
        sk[rr, cc] = False
    return sk

def ridge_geometry(elevation, cell_m, rules=DEFAULT_RULES):
    """Route a connected upper-landform network across actual crest elevations.

    The upper-landform footprint supplies topology only. Its medial line is
    refined using an elevation-deficit cost to favor the higher ground across
    an asymmetric footprint. Separate upper-lip and narrow-corridor checks
    qualify standing surfaces before aerial rock evidence is applied. No trail,
    aerial, known viewpoint, or direction enters this terrain calculation.
    """
    z = np.asarray(elevation, dtype=np.float32)
    smooth = gaussian_filter(z, rules.ridge_scale_m / cell_m)
    gy, gx = np.gradient(smooth, cell_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    radius = math.ceil(200 / cell_m)
    low = minimum_filter(smooth, size=2 * radius + 1)
    high = maximum_filter(smooth, size=2 * radius + 1)
    relative_height = (smooth - low) / np.maximum(high - low, 1)
    tpi = smooth - gaussian_filter(smooth, 80 / cell_m)
    domain = (relative_height > .65) & (tpi > 5)
    close_radius = max(1, round(4 / cell_m))
    domain = binary_closing(domain, structure=np.ones((2 * close_radius + 1,) * 2))
    # Fill only tiny numerical holes; actual depressions remain outside support.
    holes, _ = label(~domain)
    sizes = np.bincount(holes.ravel())
    small_holes = sizes < math.ceil(240 / cell_m ** 2)
    small_holes[0] = False
    domain |= small_holes[holes]
    domain = remove_short_components(domain, math.ceil(400 / cell_m ** 2))
    border = math.ceil(85 / cell_m)
    domain[:border] = domain[-border:] = False
    domain[:, :border] = domain[:, -border:] = False
    raw = prune_ridge_branches(skeletonize(domain), 36, cell_m)
    degree = convolve(raw.astype(np.uint8), np.ones((3, 3), np.uint8)) - raw
    nodes, _ = label(raw & (degree != 2), structure=np.ones((3, 3)))
    chains, _ = label(raw & (nodes == 0), structure=np.ones((3, 3)))
    top_radius = math.ceil(rules.top_neighborhood_m / cell_m)
    local_top = maximum_filter(smooth, size=2 * top_radius + 1)
    deficit = local_top - smooth
    raw_distance = distance_transform_edt(~raw) * cell_m
    cost = (1 + (deficit / 1.5) ** 2 + np.maximum(slope - 15, 0) ** 2 / 100
            + raw_distance ** 2 / 400)
    cost[~domain] = np.inf
    positions = {}
    for index, block in enumerate(find_objects(nodes), 1):
        if block is None:
            continue
        rr, cc = np.nonzero(nodes[block] == index)
        cy = int(rr.mean()) + block[0].start
        cx = int(cc.mean()) + block[1].start
        radius = math.ceil((24 if len(rr) == 1 else 12) / cell_m)
        y0, y1 = max(0, cy - radius), min(z.shape[0], cy + radius + 1)
        x0, x1 = max(0, cx - radius), min(z.shape[1], cx + radius + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        penalty = cost[y0:y1, x0:x1] + ((yy - cy) ** 2 + (xx - cx) ** 2) * cell_m ** 2 / 144
        ry, rx = np.unravel_index(np.argmin(penalty), penalty.shape)
        positions[index] = (ry + y0, rx + x0)
    ridge = np.zeros_like(domain)
    pad = math.ceil(30 / cell_m)
    for index, block in enumerate(find_objects(chains), 1):
        if block is None:
            continue
        y0, y1 = max(0, block[0].start - pad), min(z.shape[0], block[0].stop + pad)
        x0, x1 = max(0, block[1].start - pad), min(z.shape[1], block[1].stop + pad)
        chain = chains[y0:y1, x0:x1] == index
        ids = np.unique(nodes[y0:y1, x0:x1][binary_dilation(chain, structure=np.ones((3, 3)))])
        ids = ids[ids > 0]
        if len(ids) != 2:
            continue
        start, end = [positions[int(i)] for i in ids]
        y0, x0 = min(y0, start[0], end[0]), min(x0, start[1], end[1])
        y1, x1 = max(y1, start[0] + 1, end[0] + 1), max(x1, start[1] + 1, end[1] + 1)
        try:
            path, _ = route_through_array(cost[y0:y1, x0:x1],
                (start[0] - y0, start[1] - x0), (end[0] - y0, end[1] - x0),
                fully_connected=True, geometric=True)
        except ValueError:
            # Never connect landforms across a valley or an unsupported gap.
            continue
        rr, cc = np.asarray(path).T
        ridge[rr + y0, cc + x0] = True
    ridge = skeletonize(ridge)
    ridge = remove_short_components(ridge, math.ceil(rules.minimum_segment_m / cell_m))
    if not ridge.any():
        empty = np.zeros_like(domain)
        return {'ridge': empty, 'corridor': empty, 'slope': slope,
                'distance': np.full(z.shape, np.inf), 'below_crest': np.full(z.shape, np.inf),
                'narrow_crest': empty, 'terrain_top': empty}
    distance, nearest = distance_transform_edt(~ridge, sampling=cell_m, return_indices=True)
    below_crest = smooth[nearest[0], nearest[1]] - smooth
    # A flat upper lip must not inherit the slope of the cliff below it.
    # Measure the steepest UPWARD grade to adjacent native ground cells; a
    # downward cliff neighbor is not part of the standing surface. Connected
    # aerial rock and a cliff break must still qualify any off-spine platform.
    upward_grade = np.zeros_like(z)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr or dc:
                neighbor = np.roll(z, (dr, dc), axis=(0, 1))
                upward_grade = np.maximum(upward_grade, (neighbor - z) / (cell_m * math.hypot(dr, dc)))
    standing_slope = np.degrees(np.arctan(upward_grade))
    terrain_top = domain & (standing_slope <= rules.max_standing_slope_deg)
    narrow_crest = (terrain_top & (distance <= rules.corridor_radius_m)
                    & (below_crest <= rules.corridor_max_below_crest_m))
    return {'ridge': ridge, 'corridor': remove_short_components(terrain_top, 4),
            'slope': standing_slope, 'distance': distance, 'below_crest': below_crest,
            'narrow_crest': narrow_crest, 'terrain_top': terrain_top}


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
    six of seven rays: <=3° measured horizon and >=10 m fall-away within 80 m.
    A passing direction is retained independently of the opposite score.
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
            near_drop = np.nan_to_num(np.max(z[rows, cols, None] - terrain[:, distances <= rules.near_view_distance_m], axis=1), nan=0)
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
        result[rows, cols] = np.where(best > 0, .65 + .35 * best * open_ground[rows, cols], 0)
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
    # Diagnostic 2 displays the narrow crest plus actual rock-qualified tops,
    # never the broad terrain-search footprint.
    geometry['corridor'] = geometry['narrow_crest'] | candidates
    known = return_count > 0
    horizon = measured_horizon_surface(elevation, canopy_surface, known, cell_m, rules)
    sunrise = directional_pass(elevation, canopy_surface, known, candidates, openness, cell_m, (58, 90, 122), rules, horizon)
    sunset = directional_pass(elevation, canopy_surface, known, candidates, openness, cell_m, (238, 270, 302), rules, horizon)
    # Both directions must qualify independently; do not manufacture the weaker
    # direction from a shared elevation or aspect score.
    fade_ground = geometry['corridor']
    rise_seeds = select_seeds(sunrise, cell_m, minimum_strength=rules.minimum_seed_strength)
    set_seeds = select_seeds(sunset, cell_m, minimum_strength=rules.minimum_seed_strength)
    return {**geometry, 'overlooks': overlooks, 'classes': classes, 'openness': openness,
            'sunrise_pass': sunrise, 'sunset_pass': sunset,
            'sunrise': crest_fade(fade_ground, rise_seeds, sunrise, openness, cell_m, rules),
            'sunset': crest_fade(fade_ground, set_seeds, sunset, openness, cell_m, rules),
            'sunrise_seeds': rise_seeds, 'sunset_seeds': set_seeds}
