import fs from 'node:fs/promises';
import path from 'node:path';

const ROUTES_DIR = path.join(process.cwd(), 'src', 'data', 'routes');
const PUBLIC_DIR = path.join(process.cwd(), 'public');
const SERVICE = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples';
const METERS_TO_FEET = 3.280839895013123;
const EARTH_RADIUS_M = 6371008.8;

const radians = (value) => value * Math.PI / 180;
const haversineMeters = ([lon1, lat1], [lon2, lat2]) => {
  const dLat = radians(lat2 - lat1);
  const dLon = radians(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
};

function resampleLine(coords, count) {
  const cumulative = [0];
  for (let i = 1; i < coords.length; i += 1) {
    cumulative.push(cumulative[i - 1] + haversineMeters(coords[i - 1], coords[i]));
  }
  const total = cumulative.at(-1);
  if (!Number.isFinite(total) || total <= 0) throw new Error('Route geometry has no measurable length.');
  const points = [];
  for (let i = 0; i < count; i += 1) {
    const target = total * i / (count - 1);
    let segment = 1;
    while (segment < cumulative.length && cumulative[segment] < target) segment += 1;
    if (segment >= cumulative.length) {
      points.push(coords.at(-1));
      continue;
    }
    const startD = cumulative[segment - 1];
    const endD = cumulative[segment];
    const ratio = endD === startD ? 0 : (target - startD) / (endD - startD);
    const [lonA, latA] = coords[segment - 1];
    const [lonB, latB] = coords[segment];
    points.push([lonA + (lonB - lonA) * ratio, latA + (latB - latA) * ratio]);
  }
  return { points, totalMeters: total };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchChunk(points) {
  const geometry = JSON.stringify({ points, spatialReference: { wkid: 4326 } });
  const params = new URLSearchParams({
    f: 'json',
    geometry,
    geometryType: 'esriGeometryMultipoint',
    returnFirstValueOnly: 'true',
    interpolation: 'RSP_BilinearInterpolation',
    outSR: '4326'
  });
  const url = `${SERVICE}?${params.toString()}`;
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(30000) });
      if (!response.ok) throw new Error(`USGS 3DEP HTTP ${response.status}`);
      const payload = await response.json();
      if (payload.error) throw new Error(`USGS 3DEP error: ${JSON.stringify(payload.error)}`);
      if (!Array.isArray(payload.samples) || payload.samples.length !== points.length) {
        throw new Error(`Expected ${points.length} elevation samples, received ${payload.samples?.length ?? 0}`);
      }
      return payload.samples;
    } catch (error) {
      lastError = error;
      if (attempt < 3) await sleep(1000 * attempt);
    }
  }
  throw lastError;
}

function valueMeters(sample) {
  const raw = Array.isArray(sample.value) ? sample.value[0] : String(sample.value).trim().split(/\s+/)[0];
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`Invalid elevation sample: ${JSON.stringify(sample)}`);
  return value;
}

async function generateForRoute(route) {
  const geometryFile = path.join(PUBLIC_DIR, route.webGeometry.publicPath.replace(/^\//, ''));
  const geojson = JSON.parse(await fs.readFile(geometryFile, 'utf8'));
  const line = geojson.features.find((feature) => feature.geometry?.type === 'LineString' && feature.properties?.routeId === route.routeId);
  if (!line) throw new Error(`No approved LineString found for ${route.routeId}`);

  const { points: samplePoints } = resampleLine(line.geometry.coordinates, route.elevation.sampleCount);
  const samples = [];
  for (let offset = 0; offset < samplePoints.length; offset += 20) {
    const chunk = samplePoints.slice(offset, offset + 20);
    samples.push(...await fetchChunk(chunk));
  }

  let cumulativeMiles = 0;
  let ascentFt = 0;
  let descentFt = 0;
  const profile = samplePoints.map((coord, index) => {
    if (index > 0) cumulativeMiles += haversineMeters(samplePoints[index - 1], coord) / 1609.344;
    const elevationFt = valueMeters(samples[index]) * METERS_TO_FEET;
    if (index > 0) {
      const previousFt = valueMeters(samples[index - 1]) * METERS_TO_FEET;
      const delta = elevationFt - previousFt;
      if (delta > 0) ascentFt += delta;
      else descentFt += Math.abs(delta);
    }
    return {
      distanceMi: Number(cumulativeMiles.toFixed(4)),
      elevationFt: Number(elevationFt.toFixed(1))
    };
  });

  const elevations = profile.map((point) => point.elevationFt);
  const output = {
    routeId: route.routeId,
    slug: route.id,
    source: {
      id: route.elevation.sourceId,
      name: 'USGS 3DEP Bare Earth DEM — 3DEPElevation ImageServer',
      service: 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer',
      method: route.elevation.method,
      dataPublishedThrough: '2026-08-24',
      lastVerified: '2026-09-23'
    },
    stats: {
      ascentFt: Math.round(ascentFt),
      descentFt: Math.round(descentFt),
      minElevationFt: Math.round(Math.min(...elevations)),
      maxElevationFt: Math.round(Math.max(...elevations))
    },
    sampleCount: profile.length,
    points: profile
  };

  const outputFile = path.join(PUBLIC_DIR, route.elevation.publicPath.replace(/^\//, ''));
  await fs.mkdir(path.dirname(outputFile), { recursive: true });
  await fs.writeFile(outputFile, JSON.stringify(output, null, 2) + '\n');
  console.log(`Generated elevation profile: ${route.id} — ${profile.length} samples, ${output.stats.minElevationFt}-${output.stats.maxElevationFt} ft`);
}

const files = (await fs.readdir(ROUTES_DIR)).filter((name) => name.endsWith('.json')).sort();
for (const file of files) {
  const route = JSON.parse(await fs.readFile(path.join(ROUTES_DIR, file), 'utf8'));
  route.id = file.replace(/\.json$/, '');
  if (route.publicationStatus !== 'Approved — Publication Ready') continue;
  await generateForRoute(route);
}
