import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const ROOT = process.cwd();
const ROUTES_DIR = path.join(ROOT, 'src', 'data', 'routes');
const PUBLIC_DIR = path.join(ROOT, 'public');

const sha256 = (buffer) => crypto.createHash('sha256').update(buffer).digest('hex');
const fail = (message) => { throw new Error(message); };

const privatePatterns = [
  /drive\.google\.com/i,
  /1w0Uq5LPJxmVKEQCqJ6SIvdSGOEAnP_lM/,
  /1PaL0N8YX811a7q0n5X7rmvT4DYVil6HK/,
  /Gaia GPS GPX/i,
  /PROPOSED/i,
  /RAW Gaia/i,
  /eagle.?nest/i
];

const routeFiles = fs.readdirSync(ROUTES_DIR).filter((name) => name.endsWith('.json')).sort();
if (!routeFiles.length) fail('No approved route data files found.');

for (const filename of routeFiles) {
  const slug = filename.replace(/\.json$/, '');
  const route = JSON.parse(fs.readFileSync(path.join(ROUTES_DIR, filename), 'utf8'));
  if (route.publicationStatus !== 'Approved — Publication Ready') fail(`${slug}: public route is not publication-ready`);
  if (!['A','B','C'].includes(route.publicationClass)) fail(`${slug}: invalid public class`);
  if (!Array.isArray(route.publicWaypoints)) fail(`${slug}: publicWaypoints must be an array`);

  const gpxPath = path.join(PUBLIC_DIR, route.approvedPublicationGpx.publicPath.replace(/^\//, ''));
  const geoPath = path.join(PUBLIC_DIR, route.webGeometry.publicPath.replace(/^\//, ''));
  const elevationPath = path.join(PUBLIC_DIR, route.elevation.publicPath.replace(/^\//, ''));
  for (const required of [gpxPath, geoPath, elevationPath]) {
    if (!fs.existsSync(required)) fail(`${slug}: missing required public artifact ${required}`);
  }

  const gpx = fs.readFileSync(gpxPath);
  const geo = fs.readFileSync(geoPath);
  if (sha256(gpx) !== route.approvedPublicationGpx.sha256) fail(`${slug}: approved GPX hash mismatch`);
  if (sha256(geo) !== route.webGeometry.sha256) fail(`${slug}: approved GeoJSON hash mismatch`);

  const gpxText = gpx.toString('utf8');
  if (!gpxText.includes('version="1.1"')) fail(`${slug}: GPX is not 1.1`);
  if ((gpxText.match(/<trkpt\b/g) || []).length !== route.approvedPublicationGpx.trackPointCount) fail(`${slug}: GPX track-point count mismatch`);
  if ((gpxText.match(/<wpt\b/g) || []).length !== route.approvedPublicationGpx.waypointCount) fail(`${slug}: GPX waypoint count mismatch`);
  if (/<time>|<ele>|Gaia/i.test(gpxText)) fail(`${slug}: GPX contains prohibited recording/elevation metadata`);

  const geojson = JSON.parse(geo.toString('utf8'));
  const line = geojson.features.filter((f) => f.geometry?.type === 'LineString');
  const points = geojson.features.filter((f) => f.geometry?.type === 'Point');
  if (line.length !== 1) fail(`${slug}: expected exactly one approved route LineString`);
  if (points.length !== route.publicWaypoints.length) fail(`${slug}: public waypoint count does not match approved package`);
  for (const waypoint of route.publicWaypoints) {
    const feature = points.find((f) => f.properties?.waypointId === waypoint.waypointId);
    if (!feature) fail(`${slug}: missing approved waypoint ${waypoint.waypointId}`);
    const [lon, lat] = feature.geometry.coordinates;
    if (lat !== waypoint.lat || lon !== waypoint.lon || feature.properties?.name !== waypoint.name) {
      fail(`${slug}: approved waypoint data mismatch for ${waypoint.waypointId}`);
    }
  }

  const elevation = JSON.parse(fs.readFileSync(elevationPath, 'utf8'));
  if (elevation.routeId !== route.routeId || elevation.sampleCount !== route.elevation.sampleCount) fail(`${slug}: elevation profile contract mismatch`);
  if (!Array.isArray(elevation.points) || elevation.points.length !== route.elevation.sampleCount) fail(`${slug}: elevation sample count mismatch`);
  let previous = -Infinity;
  for (const point of elevation.points) {
    if (!Number.isFinite(point.distanceMi) || !Number.isFinite(point.elevationFt)) fail(`${slug}: invalid elevation sample`);
    if (point.distanceMi < previous) fail(`${slug}: elevation profile distance is not monotonic`);
    previous = point.distanceMi;
  }

  const publicCombined = [fs.readFileSync(path.join(ROUTES_DIR, filename),'utf8'), gpxText, geo.toString('utf8'), fs.readFileSync(elevationPath,'utf8')].join('\n');
  for (const pattern of privatePatterns) {
    if (pattern.test(publicCombined)) fail(`${slug}: private/superseded/sensitive source content leaked to public route artifacts: ${pattern}`);
  }
}

console.log(`Route data contract PASS: ${routeFiles.length} approved route(s); GPX/GeoJSON/elevation hashes and public waypoint inventory verified.`);
