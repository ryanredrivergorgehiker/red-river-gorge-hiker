import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const output = path.join(ROOT, 'public', 'data', 'map', 'usfs-trails.geojson');
const service = 'https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublishWithDataStatus_01/MapServer/0';
const params = new URLSearchParams({
  where: '1=1',
  geometry: '-84.02,37.52,-83.18,38.15',
  geometryType: 'esriGeometryEnvelope',
  inSR: '4326',
  spatialRel: 'esriSpatialRelIntersects',
  outFields: 'trail_name,trail_no,trail_class,attributesubset',
  returnGeometry: 'true',
  outSR: '4326',
  f: 'geojson'
});
const url = service + '/query?' + params.toString();
const response = await fetch(url, {
  headers: { Origin: 'https://redrivergorgehiker.com' },
  signal: AbortSignal.timeout(45000)
});
if (!response.ok) throw new Error('USDA Forest Service trail service HTTP ' + response.status);
const data = await response.json();
if (data?.error) throw new Error('USDA Forest Service trail service: ' + JSON.stringify(data.error));
if (data?.type !== 'FeatureCollection' || !Array.isArray(data.features) || data.features.length < 10) {
  throw new Error('USDA Forest Service trail service returned insufficient GeoJSON coverage');
}
const numbers = new Set(data.features.flatMap((feature) => {
  const p = feature?.properties || {};
  return [p.trail_no, p.TRAIL_NO].filter(Boolean).map(String);
}));
for (const required of ['214','233']) {
  if (!numbers.has(required)) throw new Error('USDA Forest Service trail cache missing required Gorge trail ' + required);
}
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, JSON.stringify(data));
console.log('Forest Service trail cache generated: ' + data.features.length + ' features; Trails 214 and 233 present.');
