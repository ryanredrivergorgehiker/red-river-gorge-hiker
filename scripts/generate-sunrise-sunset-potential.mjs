import fs from 'node:fs/promises';
import path from 'node:path';

const SERVICE = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples';
const OUTPUT_DIR = path.join(process.cwd(), 'public', 'data', 'map');
const SVG_PATH = path.join(OUTPUT_DIR, 'sunrise-sunset-potential.svg');
const META_PATH = path.join(OUTPUT_DIR, 'sunrise-sunset-potential.meta.json');

// Match the fixed Red River Gorge planning/query area used by the map.
const BOUNDS = {
  west: -84.02,
  south: 37.52,
  east: -83.18,
  north: 38.15
};

const COLS = 181;
const ROWS = 141;
const SAMPLE_TILES_X = 5;
const SAMPLE_TILES_Y = 5;
const SAMPLES_PER_TILE = 1000;
const SAMPLE_CONCURRENCY = 5;
const HORIZON_STEPS = 12;
const PROMINENCE_RADIUS = 7;
const SUNRISE_AZIMUTHS = [58, 90, 121];
const SUNSET_AZIMUTHS = [239, 270, 302];
const SUNRISE_COLOR = '#ff6f61';
const SUNSET_COLOR = '#4055d8';
const VERSION = 1;

const clamp01 = (value) => Math.max(0, Math.min(1, value));
const radians = (degrees) => degrees * Math.PI / 180;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchEnvelopeSamples(bounds) {
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
      const response = await fetch(SERVICE, {
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
  const responses = await Promise.all(batch.map((bounds) => fetchEnvelopeSamples(bounds)));

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

  const completed = Math.min(offset + batch.length, sampleTiles.length);
  console.log(`USGS 3DEP sunrise/sunset area sampling: ${completed}/${sampleTiles.length} tiles; ${returnedSampleCount} samples returned`);
}

const elevations = sums.map((sum, index) => counts[index] ? sum / counts[index] : null);
const at = (row, col, grid = elevations) => {
  if (row < 0 || row >= ROWS || col < 0 || col >= COLS) return null;
  return grid[row * COLS + col] ?? null;
};

// Area sampling is dense but does not promise one returned point per output cell.
// Fill sparse cells from nearby sampled terrain without inventing values beyond the sampled extent.
for (let pass = 0; pass < 10 && elevations.some((value) => value === null); pass += 1) {
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

function localProminence(row, col, elevation) {
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
  if (high - low < 1) return 0.5;
  return clamp01((elevation - low) / (high - low));
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

  if (maxHorizon === -Math.PI / 2) return 0.5;
  const horizonDegrees = maxHorizon * 180 / Math.PI;
  return clamp01((8 - horizonDegrees) / 12);
}

function seasonalPotential(row, col, elevation, azimuths, prominence) {
  const values = azimuths.map((azimuth) => {
    const open = directionalOpenness(row, col, elevation, azimuth);
    return 0.76 * open + 0.24 * prominence;
  });
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  const best = Math.max(...values);
  return clamp01(0.62 * average + 0.38 * best);
}

const sunrise = new Array(elevations.length).fill(0);
const sunset = new Array(elevations.length).fill(0);
for (let row = 0; row < ROWS; row += 1) {
  for (let col = 0; col < COLS; col += 1) {
    const index = row * COLS + col;
    const elevation = elevations[index];
    if (elevation === null) continue;
    const prominence = localProminence(row, col, elevation);
    sunrise[index] = seasonalPotential(row, col, elevation, SUNRISE_AZIMUTHS, prominence);
    sunset[index] = seasonalPotential(row, col, elevation, SUNSET_AZIMUTHS, prominence);
  }
}

const OPACITY_LEVELS = [0.11, 0.18, 0.27, 0.37, 0.48, 0.59, 0.69, 0.78];
const paths = {
  sunrise: OPACITY_LEVELS.map(() => []),
  sunset: OPACITY_LEVELS.map(() => [])
};

function opacityBucket(score) {
  const strength = clamp01((score - 0.40) / 0.48);
  if (strength <= 0) return -1;
  return Math.min(OPACITY_LEVELS.length - 1, Math.floor(strength * OPACITY_LEVELS.length));
}

function addCell(target, bucket, row, col) {
  if (bucket < 0) return;
  target[bucket].push(`M${col} ${row}h1v1h-1z`);
}

for (let row = 0; row < ROWS - 1; row += 1) {
  for (let col = 0; col < COLS - 1; col += 1) {
    const index = row * COLS + col;
    addCell(paths.sunrise, opacityBucket(sunrise[index]), row, col);
    addCell(paths.sunset, opacityBucket(sunset[index]), row, col);
  }
}

const escapeXml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

const metadata = {
  version: VERSION,
  generatedAtUtc: new Date().toISOString(),
  source: {
    id: 'usgs-3dep-bare-earth-dem',
    service: SERVICE.replace('/getSamples', ''),
    interpolation: 'RSP_BilinearInterpolation'
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
  method: 'Terrain-derived photographic potential using local prominence and directional terrain-horizon clearance.',
  seasonalAzimuths: {
    sunrise: SUNRISE_AZIMUTHS,
    sunset: SUNSET_AZIMUTHS,
    note: 'Representative summer/equinox/winter directions for the Red River Gorge latitude; not a date-specific solar ephemeris.'
  },
  display: {
    sunriseColor: SUNRISE_COLOR,
    sunsetColor: SUNSET_COLOR,
    maximumOpacity: OPACITY_LEVELS.at(-1),
    lowPotentialTransparent: true
  },
  limitations: [
    'Bare-earth terrain model only.',
    'Does not account for current weather, haze, vegetation, buildings, seasonal foliage, or local obstructions not represented by the DEM.',
    'Potential is year-round/seasonal and is not a guarantee of visible sunrise or sunset.'
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

console.log(`Generated ${path.relative(process.cwd(), SVG_PATH)} and metadata from ${returnedSampleCount} USGS terrain samples.`);
