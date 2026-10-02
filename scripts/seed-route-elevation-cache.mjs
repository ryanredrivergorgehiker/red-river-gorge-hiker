import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const ROOT = process.cwd();
const ROUTES_DIR = path.join(ROOT, 'src', 'data', 'routes');
const PUBLIC_DIR = path.join(ROOT, 'public');
const CACHE_DIR = path.join(ROOT, '.ci-cache');
const sha256 = (buffer) => crypto.createHash('sha256').update(buffer).digest('hex');
const fail = (message) => { throw new Error(message); };
const elevationInputFingerprint = (route) => sha256(Buffer.from(JSON.stringify({
  routeId: route.routeId,
  webGeometrySha256: route.webGeometry.sha256,
  approvedPublicationGpxSha256: route.approvedPublicationGpx.sha256,
  trackPointCount: route.approvedPublicationGpx.trackPointCount,
  waypointCount: route.approvedPublicationGpx.waypointCount,
  sourceId: route.elevation.sourceId,
  sampleCount: route.elevation.sampleCount,
  method: route.elevation.method
})));

const files = fs.readdirSync(ROUTES_DIR).filter((name) => name.endsWith('.json')).sort();
for (const file of files) {
  const slug = file.replace(/\.json$/, '');
  const route = JSON.parse(fs.readFileSync(path.join(ROUTES_DIR, file), 'utf8'));
  if (route.publicationStatus !== 'Approved — Publication Ready') continue;
  const geoPath = path.join(PUBLIC_DIR, route.webGeometry.publicPath.replace(/^\//, ''));
  if (!fs.existsSync(geoPath) || sha256(fs.readFileSync(geoPath)) !== route.webGeometry.sha256) fail(`${slug}: approved GeoJSON identity mismatch before cache seed`);
  const gpx = route.approvedPublicationGpx;
  if (gpx.publicDownload) {
    if (!gpx.publicPath) fail(`${slug}: public GPX requires publicPath`);
    const gpxPath = path.join(PUBLIC_DIR, gpx.publicPath.replace(/^\//, ''));
    if (!fs.existsSync(gpxPath) || sha256(fs.readFileSync(gpxPath)) !== gpx.sha256) fail(`${slug}: public GPX identity mismatch before cache seed`);
  } else {
    if (gpx.publicPath) fail(`${slug}: controlled GPX must not define publicPath`);
    if (fs.existsSync(path.join(PUBLIC_DIR, 'downloads', 'routes', gpx.filename))) fail(`${slug}: controlled GPX leaked into public downloads`);
  }
  const cachePath = path.join(CACHE_DIR, `${slug}.elevation.json`);
  if (!fs.existsSync(cachePath)) fail(`${slug}: deterministic elevation cache is missing`);
  const cache = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
  if (cache.inputFingerprint !== elevationInputFingerprint(route)) fail(`${slug}: elevation cache input fingerprint mismatch`);
  if (cache.routeId !== route.routeId || cache.slug !== slug) fail(`${slug}: elevation cache route identity mismatch`);
  if (cache.source?.id !== route.elevation.sourceId || cache.source?.method !== route.elevation.method) fail(`${slug}: elevation cache source/method mismatch`);
  if (cache.sampleCount !== route.elevation.sampleCount || !Array.isArray(cache.points) || cache.points.length !== route.elevation.sampleCount) fail(`${slug}: elevation cache sample count mismatch`);
  for (const key of ['ascentFt','descentFt','minElevationFt','maxElevationFt']) if (!Number.isFinite(cache.stats?.[key])) fail(`${slug}: elevation cache missing numeric ${key}`);
  const output = path.join(PUBLIC_DIR, route.elevation.publicPath.replace(/^\//, ''));
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.copyFileSync(cachePath, output);
  console.log(`Seeded validated elevation cache: ${slug} — ${cache.sampleCount} samples`);
}
