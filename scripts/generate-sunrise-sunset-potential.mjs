import fs from 'node:fs/promises';
import path from 'node:path';

const ELEVATION_SERVICE = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples';
const HYDRO_SERVICE = 'https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer';
const OUTPUT_DIR = path.join(process.cwd(), 'public', 'data', 'map');
const SVG_PATH = path.join(OUTPUT_DIR, 'sunrise-sunset-potential.svg');
const META_PATH = path.join(OUTPUT_DIR, 'sunrise-sunset-potential.meta.json');

// Fixed Red River Gorge planning/query area used by the map.
const BOUNDS = {
  west: -84.02,
  south: 37.52,
  east: -83.18,
  north: 38.15
};

// V2 intentionally uses a denser grid and a much more conservative high-ground model.
const COLS = 271;
const ROWS = 211;
const SAMPLE_TILES_X = 7;
const SAMPLE_TILES_Y = 7;
const SAMPLES_PER_TILE = 1000;
const SAMPLE_CONCURRENCY = 7;
const HORIZON_STEPS = 18;
const PROMINENCE_RADIUS = 9;
const CONVEXITY_RADIUS = 3;
const MIN_LOCAL_RELIEF_METERS = 42;
const MIN_PROMINENCE = 0.64;
const MIN_CONVEXITY = 0.34;
const MIN_DIRECTIONAL_OPENNESS = 0.58;
const MIN_DISPLAY_SCORE = 0.70;
const DISPLAY_CANDIDATE_QUANTILE = 0.45;
const FLOWLINE_EXCLUSION_BUFFER_METERS = 300;
const SUNRISE_AZIMUTHS = [58, 90, 121];
const SUNSET_AZIMUTHS = [239, 270, 302];
const SUNRISE_COLOR = '#ff6f61';
const SUNSET_COLOR = '#4055d8';
const VERSION = 2;

const clamp01 = (value) => Math.max(0, Math.min(1, value));
const radians = (degrees) => degrees * Math.PI / 180;
const degrees = (radiansValue) => radiansValue * 180 / Math.PI;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function quantile(values, q) {
  const sorted = values.filter(Number.isFinite).slice().sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const position = (sorted.length - 1) * clamp01(q);
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  const fraction = position - lower;
  return sorted[lower] * (1 - fraction) + sorted[upper] * fraction;
}

async function fetchElevationEnvelopeSamples(bounds) {
  const geometry = JSON.stringify({
    xmin: bounds.west,
    ymin: bounds.south,
    xmax: bounds.east,
    ymax: bounds.north,
    spatialReference: { wkid: 4326 }
  });
  const body = new URLSearchParams({
    f: 'json',
    geometry,
    geometryType: 'esriGeometryEnvelope',
    sampleCount: String(SAMPLES_PER_TILE),
    returnFirstValueOnly: 'true',
    interpolation: 'RSP_BilinearInterpolation',
    outSR: '4326'
  });

  let lastError;
  for (let attempt = 1; attempt <= 4; attempt += 1) {
    try {
      const response = await fetch(ELEVATION_SERVICE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
        body,
        signal: AbortSignal.timeout(45000)
      });
      if (!response.ok) throw new Error(`USGS 3DEP HTTP ${response.status}`);
      const payload = await response.json();
      if (payload.error) throw new Error(`USGS 3DEP error: ${JSON.stringify(payload.error)}`);
      if (!Array.isArray(payload.samples) || payload.samples.length === 0) {
        throw new Error('USGS 3DEP returned no area samples.');
      }
      return payload.samples;
    } catch (error) {
      lastError = error;
      if (attempt < 4) await sleep(1000 * attempt);
    }
  }
  throw lastError;
}

async function fetchHydroLayer(layerId) {
  const features = [];
  const pageSize = 2000;

  for (let offset = 0; ; offset += pageSize) {
    const url = new URL(`${HYDRO_SERVICE}/${layerId}/query`);
    url.searchParams.set('f', 'geojson');
    url.searchParams.set('where', '1=1');
    url.searchParams.set('geometry', JSON.stringify({
      xmin: BOUNDS.west,
      ymin: BOUNDS.south,
      xmax: BOUNDS.east,
      ymax: BOUNDS.north,
      spatialReference: { wkid: 4326 }
    }));
    url.searchParams.set('geometryType', 'esriGeometryEnvelope');
    url.searchParams.set('inSR', '4326');
    url.searchParams.set('outSR', '4326');
    url.searchParams.set('spatialRel', 'esriSpatialRelIntersects');
    url.searchParams.set('outFields', 'OBJECTID,FTYPE,FCODE,GNIS_NAME');
    url.searchParams.set('returnGeometry', 'true');
    url.searchParams.set('resultOffset', String(offset));
    url.searchParams.set('resultRecordCount', String(pageSize));
    url.searchParams.set('orderByFields', 'OBJECTID ASC');

    let payload = null;
    let lastError;
    for (let attempt = 1; attempt <= 4; attempt += 1) {
      try {
        const response = await fetch(url, { signal: AbortSignal.timeout(45000) });
        if (!response.ok) throw new Error(`USGS NHDPlus HR layer ${layerId} HTTP ${response.status}`);
        payload = await response.json();
        if (payload.error) throw new Error(`USGS NHDPlus HR layer ${layerId} error: ${JSON.stringify(payload.error)}`);
        break;
      } catch (error) {
        lastError = error;
        if (attempt < 4) await sleep(1000 * attempt);
      }
    }
    if (!payload) throw lastError;
    const pageFeatures = Array.isArray(payload.features) ? payload.features : [];
    features.push(...pageFeatures);
    if (pageFeatures.length < pageSize) break;
  }

  return features;
}

function sampleMeters(sample) {
  const raw = Array.isArray(sample.value)
    ? sample.value[0]
    : String(sample.value ?? '').trim().split(/\s+/)[0];
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

const sums = new Array(COLS * ROWS).fill(0);
const counts = new Array(COLS * ROWS).fill(0);
let returnedSampleCount = 0;

const sampleTiles = [];
for (let tileY = 0; tileY < SAMPLE_TILES_Y; tileY += 1) {
  for (let tileX = 0; tileX < SAMPLE_TILES_X; tileX += 1) {
    sampleTiles.push({
      west: BOUNDS.west + (tileX / SAMPLE_TILES_X) * (BOUNDS.east - BOUNDS.west),
      east: BOUNDS.west + ((tileX + 1) / SAMPLE_TILES_X) * (BOUNDS.east - BOUNDS.west),
      north: BOUNDS.north - (tileY / SAMPLE_TILES_Y) * (BOUNDS.north - BOUNDS.south),
      south: BOUNDS.north - ((tileY + 1) / SAMPLE_TILES_Y) * (BOUNDS.north - BOUNDS.south)
    });
  }
}

for (let offset = 0; offset < sampleTiles.length; offset += SAMPLE_CONCURRENCY) {
  const batch = sampleTiles.slice(offset, offset + SAMPLE_CONCURRENCY);
  const responses = await Promise.all(batch.map((bounds) => fetchElevationEnvelopeSamples(bounds)));

  for (const samples of responses) {
    returnedSampleCount += samples.length;
    for (const sample of samples) {
      const elevation = sampleMeters(sample);
      const lon = Number(sample.location?.x);
      const lat = Number(sample.location?.y);
      if (elevation === null || !Number.isFinite(lon) || !Number.isFinite(lat)) continue;
      const col = Math.max(0, Math.min(COLS - 1, Math.round((lon - BOUNDS.west) / (BOUNDS.east - BOUNDS.west) * (COLS - 1))));
      const row = Math.max(0, Math.min(ROWS - 1, Math.round((BOUNDS.north - lat) / (BOUNDS.north - BOUNDS.south) * (ROWS - 1))));
      const index = row * COLS + col;
      sums[index] += elevation;
      counts[index] += 1;
    }
  }

  console.log(`USGS 3DEP area sampling: ${Math.min(offset + batch.length, sampleTiles.length)}/${sampleTiles.length} tiles; ${returnedSampleCount} samples returned`);
}

const elevations = sums.map((sum, index) => counts[index] ? sum / counts[index] : null);
const at = (row, col, grid = elevations) => {
  if (row < 0 || row >= ROWS || col < 0 || col >= COLS) return null;
  return grid[row * COLS + col] ?? null;
};

// Fill sparse cells only from neighboring sampled terrain.
for (let pass = 0; pass < 14 && elevations.some((value) => value === null); pass += 1) {
  const prior = elevations.slice();
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const index = row * COLS + col;
      if (prior[index] !== null) continue;
      let weighted = 0;
      let weightTotal = 0;
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          if (!dx && !dy) continue;
          const value = at(row + dy, col + dx, prior);
          if (value === null) continue;
          const weight = dx === 0 || dy === 0 ? 1 : Math.SQRT1_2;
          weighted += value * weight;
          weightTotal += weight;
        }
      }
      if (weightTotal) elevations[index] = weighted / weightTotal;
    }
  }
}

const missingCount = elevations.filter((value) => value === null).length;
if (missingCount) throw new Error(`Terrain grid still has ${missingCount} unsampled cells after neighbor filling.`);

const midLat = (BOUNDS.south + BOUNDS.north) / 2;
const xMeters = 111320 * Math.cos(radians(midLat)) * (BOUNDS.east - BOUNDS.west) / (COLS - 1);
const yMeters = 111320 * (BOUNDS.north - BOUNDS.south) / (ROWS - 1);
const elevationValues = elevations.filter(Number.isFinite);
const elevationQ55 = quantile(elevationValues, 0.55);
const elevationQ90 = quantile(elevationValues, 0.90);

const cellLon = (col) => BOUNDS.west + (col / (COLS - 1)) * (BOUNDS.east - BOUNDS.west);
const cellLat = (row) => BOUNDS.north - (row / (ROWS - 1)) * (BOUNDS.north - BOUNDS.south);
const gridCol = (lon) => (lon - BOUNDS.west) / (BOUNDS.east - BOUNDS.west) * (COLS - 1);
const gridRow = (lat) => (BOUNDS.north - lat) / (BOUNDS.north - BOUNDS.south) * (ROWS - 1);

function pointInRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersects = ((yi > lat) !== (yj > lat))
      && (lon < (xj - xi) * (lat - yi) / ((yj - yi) || Number.EPSILON) + xi);
    if (intersects) inside = !inside;
  }
  return inside;
}

function pointInPolygon(lon, lat, rings) {
  if (!rings?.length || !pointInRing(lon, lat, rings[0])) return false;
  for (let i = 1; i < rings.length; i += 1) {
    if (pointInRing(lon, lat, rings[i])) return false;
  }
  return true;
}

const waterMask = new Array(COLS * ROWS).fill(false);
let hydroPolygonFeatures = 0;
let hydroFlowlineFeatures = 0;

function markPolygon(rings) {
  if (!rings?.length) return;
  const outer = rings[0];
  const lons = outer.map((point) => point[0]);
  const lats = outer.map((point) => point[1]);
  const minCol = Math.max(0, Math.floor(gridCol(Math.min(...lons))) - 1);
  const maxCol = Math.min(COLS - 1, Math.ceil(gridCol(Math.max(...lons))) + 1);
  const minRow = Math.max(0, Math.floor(gridRow(Math.max(...lats))) - 1);
  const maxRow = Math.min(ROWS - 1, Math.ceil(gridRow(Math.min(...lats))) + 1);

  for (let row = minRow; row <= maxRow; row += 1) {
    for (let col = minCol; col <= maxCol; col += 1) {
      if (pointInPolygon(cellLon(col), cellLat(row), rings)) {
        waterMask[row * COLS + col] = true;
      }
    }
  }
}

function markLineString(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length < 2) return;
  for (let i = 1; i < coordinates.length; i += 1) {
    const [lonA, latA] = coordinates[i - 1];
    const [lonB, latB] = coordinates[i];
    const colA = gridCol(lonA);
    const rowA = gridRow(latA);
    const colB = gridCol(lonB);
    const rowB = gridRow(latB);
    const steps = Math.max(1, Math.ceil(Math.max(Math.abs(colB - colA), Math.abs(rowB - rowA)) * 4));

    for (let step = 0; step <= steps; step += 1) {
      const t = step / steps;
      const colFloat = colA + (colB - colA) * t;
      const rowFloat = rowA + (rowB - rowA) * t;
      const colCenter = Math.round(colFloat);
      const rowCenter = Math.round(rowFloat);
      const colRadius = Math.ceil(FLOWLINE_EXCLUSION_BUFFER_METERS / xMeters) + 1;
      const rowRadius = Math.ceil(FLOWLINE_EXCLUSION_BUFFER_METERS / yMeters) + 1;

      for (let row = Math.max(0, rowCenter - rowRadius); row <= Math.min(ROWS - 1, rowCenter + rowRadius); row += 1) {
        for (let col = Math.max(0, colCenter - colRadius); col <= Math.min(COLS - 1, colCenter + colRadius); col += 1) {
          const dx = (col - colFloat) * xMeters;
          const dy = (row - rowFloat) * yMeters;
          if (Math.hypot(dx, dy) <= FLOWLINE_EXCLUSION_BUFFER_METERS) {
            waterMask[row * COLS + col] = true;
          }
        }
      }
    }
  }
}

const hydroLayers = await Promise.all([
  fetchHydroLayer(9), // NHDWaterbody polygons
  fetchHydroLayer(8), // NHDArea polygons, including stream/river areas
  fetchHydroLayer(3), // NetworkNHDFlowline
  fetchHydroLayer(4)  // NonNetworkNHDFlowline
]);

for (const feature of [...hydroLayers[0], ...hydroLayers[1]]) {
  const geometry = feature.geometry;
  if (!geometry) continue;
  if (geometry.type === 'Polygon') {
    markPolygon(geometry.coordinates);
    hydroPolygonFeatures += 1;
  } else if (geometry.type === 'MultiPolygon') {
    for (const polygon of geometry.coordinates) markPolygon(polygon);
    hydroPolygonFeatures += 1;
  }
}

for (const feature of [...hydroLayers[2], ...hydroLayers[3]]) {
  const geometry = feature.geometry;
  if (!geometry) continue;
  if (geometry.type === 'LineString') {
    markLineString(geometry.coordinates);
    hydroFlowlineFeatures += 1;
  } else if (geometry.type === 'MultiLineString') {
    for (const line of geometry.coordinates) markLineString(line);
    hydroFlowlineFeatures += 1;
  }
}

function localTerrain(row, col, elevation) {
  let low = elevation;
  let high = elevation;
  for (let r = Math.max(0, row - PROMINENCE_RADIUS); r <= Math.min(ROWS - 1, row + PROMINENCE_RADIUS); r += 1) {
    for (let c = Math.max(0, col - PROMINENCE_RADIUS); c <= Math.min(COLS - 1, col + PROMINENCE_RADIUS); c += 1) {
      const value = at(r, c);
      if (value === null) continue;
      low = Math.min(low, value);
      high = Math.max(high, value);
    }
  }
  const relief = Math.max(0, high - low);
  const prominence = relief < 1 ? 0.5 : clamp01((elevation - low) / relief);

  let ringSum = 0;
  let ringCount = 0;
  for (let dy = -CONVEXITY_RADIUS; dy <= CONVEXITY_RADIUS; dy += 1) {
    for (let dx = -CONVEXITY_RADIUS; dx <= CONVEXITY_RADIUS; dx += 1) {
      const distance = Math.hypot(dx, dy);
      if (distance < CONVEXITY_RADIUS - 0.75 || distance > CONVEXITY_RADIUS + 0.75) continue;
      const value = at(row + dy, col + dx);
      if (value === null) continue;
      ringSum += value;
      ringCount += 1;
    }
  }
  const ringAverage = ringCount ? ringSum / ringCount : elevation;
  const convexityDelta = elevation - ringAverage;
  const convexity = clamp01((convexityDelta + 4) / 22);

  return { low, high, relief, prominence, convexity, convexityDelta };
}

function slopeAspect(row, col) {
  const west = at(row, col - 1) ?? at(row, col);
  const east = at(row, col + 1) ?? at(row, col);
  const north = at(row - 1, col) ?? at(row, col);
  const south = at(row + 1, col) ?? at(row, col);
  const dzdx = (east - west) / (2 * xMeters);
  const dzdy = (north - south) / (2 * yMeters);
  const slopeRadians = Math.atan(Math.hypot(dzdx, dzdy));
  let aspect = degrees(Math.atan2(-dzdx, -dzdy));
  if (aspect < 0) aspect += 360;
  return { slopeDegrees: degrees(slopeRadians), aspect };
}

function directionalOpenness(row, col, elevation, azimuth) {
  const angle = radians(azimuth);
  const eastComponent = Math.sin(angle);
  const northComponent = Math.cos(angle);
  let maxHorizon = -Math.PI / 2;

  for (let step = 1; step <= HORIZON_STEPS; step += 1) {
    const targetCol = Math.round(col + eastComponent * step);
    const targetRow = Math.round(row - northComponent * step);
    const target = at(targetRow, targetCol);
    if (target === null) continue;
    const dx = (targetCol - col) * xMeters;
    const dy = (targetRow - row) * yMeters;
    const distance = Math.hypot(dx, dy);
    if (distance < 1) continue;
    maxHorizon = Math.max(maxHorizon, Math.atan2(target - elevation, distance));
  }

  if (maxHorizon === -Math.PI / 2) return 0;
  const horizonDegrees = degrees(maxHorizon);
  // High ridges tend to have a zero or negative horizon. Positive terrain horizons
  // are increasingly suppressed so enclosed valleys do not qualify.
  return clamp01((6 - horizonDegrees) / 12);
}

function angleDistance(a, b) {
  const delta = Math.abs(a - b) % 360;
  return Math.min(delta, 360 - delta);
}

function directionalAspectScore(aspect, slopeDegrees, azimuths) {
  const bestAlignment = Math.max(...azimuths.map((azimuth) => Math.max(0, Math.cos(radians(angleDistance(aspect, azimuth))))));
  const slopeStrength = clamp01(slopeDegrees / 16);
  // A nearly flat ridge crest is direction-neutral rather than automatically bad.
  return 0.55 * (1 - slopeStrength) + bestAlignment * slopeStrength;
}

function rawPotential(row, col, elevation, azimuths, terrain, regionalElevationScore, aspectInfo) {
  const opennessValues = azimuths.map((azimuth) => directionalOpenness(row, col, elevation, azimuth));
  const bestOpenness = Math.max(...opennessValues);
  const averageOpenness = opennessValues.reduce((sum, value) => sum + value, 0) / opennessValues.length;
  const openness = 0.58 * bestOpenness + 0.42 * averageOpenness;
  const aspect = directionalAspectScore(aspectInfo.aspect, aspectInfo.slopeDegrees, azimuths);

  if (terrain.relief < MIN_LOCAL_RELIEF_METERS) return 0;
  if (terrain.prominence < MIN_PROMINENCE) return 0;
  if (terrain.convexity < MIN_CONVEXITY) return 0;
  if (bestOpenness < MIN_DIRECTIONAL_OPENNESS) return 0;
  if (elevation < elevationQ55) return 0;

  return clamp01(
    0.34 * terrain.prominence
    + 0.22 * regionalElevationScore
    + 0.17 * terrain.convexity
    + 0.20 * openness
    + 0.07 * aspect
  );
}

const sunriseRaw = new Array(elevations.length).fill(0);
const sunsetRaw = new Array(elevations.length).fill(0);
let ridgeCandidateCells = 0;

for (let row = 0; row < ROWS; row += 1) {
  for (let col = 0; col < COLS; col += 1) {
    const index = row * COLS + col;
    const elevation = elevations[index];
    if (elevation === null || waterMask[index]) continue;

    const terrain = localTerrain(row, col, elevation);
    const regionalElevationScore = clamp01((elevation - elevationQ55) / Math.max(1, elevationQ90 - elevationQ55));
    const aspectInfo = slopeAspect(row, col);

    if (
      terrain.relief >= MIN_LOCAL_RELIEF_METERS
      && terrain.prominence >= MIN_PROMINENCE
      && terrain.convexity >= MIN_CONVEXITY
      && elevation >= elevationQ55
    ) ridgeCandidateCells += 1;

    sunriseRaw[index] = rawPotential(row, col, elevation, SUNRISE_AZIMUTHS, terrain, regionalElevationScore, aspectInfo);
    sunsetRaw[index] = rawPotential(row, col, elevation, SUNSET_AZIMUTHS, terrain, regionalElevationScore, aspectInfo);
  }
}

function displayThreshold(scores) {
  const candidates = scores.filter((value) => value > 0);
  return Math.max(MIN_DISPLAY_SCORE, quantile(candidates, DISPLAY_CANDIDATE_QUANTILE));
}

const sunriseThreshold = displayThreshold(sunriseRaw);
const sunsetThreshold = displayThreshold(sunsetRaw);
const sunriseHigh = Math.max(sunriseThreshold + 0.01, quantile(sunriseRaw.filter((value) => value > 0), 0.98));
const sunsetHigh = Math.max(sunsetThreshold + 0.01, quantile(sunsetRaw.filter((value) => value > 0), 0.98));

const OPACITY_LEVELS = [0.18, 0.29, 0.41, 0.54, 0.67, 0.79, 0.88];
const paths = {
  sunrise: OPACITY_LEVELS.map(() => []),
  sunset: OPACITY_LEVELS.map(() => [])
};

function opacityBucket(score, threshold, high) {
  if (score < threshold) return -1;
  const strength = clamp01((score - threshold) / Math.max(0.001, high - threshold));
  return Math.min(OPACITY_LEVELS.length - 1, Math.floor(strength * OPACITY_LEVELS.length));
}

function addCell(target, bucket, row, col) {
  if (bucket < 0) return;
  target[bucket].push(`M${col} ${row}h1v1h-1z`);
}

let sunriseDisplayCells = 0;
let sunsetDisplayCells = 0;
for (let row = 0; row < ROWS - 1; row += 1) {
  for (let col = 0; col < COLS - 1; col += 1) {
    const index = row * COLS + col;
    const sunriseBucket = opacityBucket(sunriseRaw[index], sunriseThreshold, sunriseHigh);
    const sunsetBucket = opacityBucket(sunsetRaw[index], sunsetThreshold, sunsetHigh);
    if (sunriseBucket >= 0) sunriseDisplayCells += 1;
    if (sunsetBucket >= 0) sunsetDisplayCells += 1;
    addCell(paths.sunrise, sunriseBucket, row, col);
    addCell(paths.sunset, sunsetBucket, row, col);
  }
}

const totalDisplayCells = (ROWS - 1) * (COLS - 1);
const waterMaskCells = waterMask.filter(Boolean).length;
const percent = (count, total) => Number((count / total * 100).toFixed(2));

const escapeXml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

const metadata = {
  version: VERSION,
  generatedAtUtc: new Date().toISOString(),
  source: {
    id: 'rrgh-high-ground-sun-potential',
    elevation: {
      id: 'usgs-3dep-bare-earth-dem',
      service: ELEVATION_SERVICE.replace('/getSamples', ''),
      interpolation: 'RSP_BilinearInterpolation'
    },
    hydrography: {
      id: 'usgs-nhdplus-hr',
      service: HYDRO_SERVICE,
      layers: {
        networkFlowline: 3,
        nonNetworkFlowline: 4,
        area: 8,
        waterbody: 9
      },
      polygonFeatures: hydroPolygonFeatures,
      flowlineFeatures: hydroFlowlineFeatures
    }
  },
  bounds: BOUNDS,
  grid: {
    cols: COLS,
    rows: ROWS,
    approximateCellMeters: [Math.round(xMeters), Math.round(yMeters)],
    samplingTiles: [SAMPLE_TILES_X, SAMPLE_TILES_Y],
    requestedSamplesPerTile: SAMPLES_PER_TILE,
    returnedSamples: returnedSampleCount
  },
  method: 'Conservative high-ground photographic potential: hard water exclusion, regional elevation floor, local relief, ridge/upper-shoulder prominence, terrain convexity, directional terrain-horizon clearance, and slope/aspect alignment.',
  thresholds: {
    elevationQ55Meters: Number(elevationQ55.toFixed(1)),
    elevationQ90Meters: Number(elevationQ90.toFixed(1)),
    minLocalReliefMeters: MIN_LOCAL_RELIEF_METERS,
    minProminence: MIN_PROMINENCE,
    minConvexity: MIN_CONVEXITY,
    minDirectionalOpenness: MIN_DIRECTIONAL_OPENNESS,
    waterFlowlineExclusionBufferMeters: FLOWLINE_EXCLUSION_BUFFER_METERS,
    sunriseDisplayScore: Number(sunriseThreshold.toFixed(4)),
    sunsetDisplayScore: Number(sunsetThreshold.toFixed(4))
  },
  seasonalAzimuths: {
    sunrise: SUNRISE_AZIMUTHS,
    sunset: SUNSET_AZIMUTHS,
    note: 'Representative summer/equinox/winter directions for the Red River Gorge latitude; not a date-specific solar ephemeris.'
  },
  coverage: {
    waterMaskCells,
    waterMaskPercent: percent(waterMaskCells, COLS * ROWS),
    ridgeCandidateCells,
    ridgeCandidatePercent: percent(ridgeCandidateCells, COLS * ROWS),
    sunriseDisplayCells,
    sunriseDisplayPercent: percent(sunriseDisplayCells, totalDisplayCells),
    sunsetDisplayCells,
    sunsetDisplayPercent: percent(sunsetDisplayCells, totalDisplayCells)
  },
  display: {
    sunriseColor: SUNRISE_COLOR,
    sunsetColor: SUNSET_COLOR,
    maximumOpacity: OPACITY_LEVELS.at(-1),
    lowPotentialTransparent: true,
    designIntent: 'Sparse ridge and upper-shoulder bands; low valleys and mapped water suppressed.'
  },
  limitations: [
    'Terrain and hydrography model only; mapped water is excluded and low/valley terrain is strongly suppressed.',
    'Does not account for current weather, haze, vegetation, buildings, seasonal foliage, access, or small local obstructions not represented by the source data.',
    'Potential is seasonal/generalized and is not a guarantee of visible sunrise, visible sunset, legal access, or a good photographic view.'
  ]
};

const pathElements = [];
for (const [kind, color] of [['sunrise', SUNRISE_COLOR], ['sunset', SUNSET_COLOR]]) {
  for (let i = 0; i < OPACITY_LEVELS.length; i += 1) {
    const d = paths[kind][i].join('');
    if (!d) continue;
    pathElements.push(`<path d="${d}" fill="${color}" fill-opacity="${OPACITY_LEVELS[i]}"/>`);
  }
}

const svg = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${COLS - 1} ${ROWS - 1}" preserveAspectRatio="none">`,
  `<metadata>${escapeXml(JSON.stringify(metadata))}</metadata>`,
  '<g shape-rendering="geometricPrecision">',
  ...pathElements,
  '</g>',
  '</svg>',
  ''
].join('\n');

await fs.mkdir(OUTPUT_DIR, { recursive: true });
await fs.writeFile(SVG_PATH, svg);
await fs.writeFile(META_PATH, JSON.stringify(metadata, null, 2) + '\n');

console.log(`Generated ${path.relative(process.cwd(), SVG_PATH)}: sunrise ${metadata.coverage.sunriseDisplayPercent}% / sunset ${metadata.coverage.sunsetDisplayPercent}% displayed; water mask ${metadata.coverage.waterMaskPercent}%.`);
