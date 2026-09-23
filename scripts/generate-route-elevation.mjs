import fs from 'node:fs/promises';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, arg, i, all) => {
  if (arg.startsWith('--')) pairs.push([arg.slice(2), all[i + 1]]);
  return pairs;
}, []));

const geometryPath = args.geometry ?? 'public/data/routes/skybridge-arch.geojson';
const outputPath = args.output ?? 'public/data/routes/skybridge-arch.elevation.json';
const geometry = JSON.parse(await fs.readFile(geometryPath, 'utf8'));
const route = geometry.features.find((feature) => feature.geometry?.type === 'LineString');
if (!route) throw new Error('No approved LineString route geometry found.');

const coords = route.geometry.coordinates;
const toRad = (n) => n * Math.PI / 180;
const haversineMiles = (a,b) => {
  const R = 3958.7613;
  const dLat = toRad(b[1]-a[1]);
  const dLon = toRad(b[0]-a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const h = Math.sin(dLat/2)**2 + Math.cos(lat1)*Math.cos(lat2)*Math.sin(dLon/2)**2;
  return 2 * R * Math.asin(Math.sqrt(h));
};

const query = async ([lon,lat]) => {
  const url = new URL('https://epqs.nationalmap.gov/v1/json');
  url.searchParams.set('x', String(lon));
  url.searchParams.set('y', String(lat));
  url.searchParams.set('wkid','4326');
  url.searchParams.set('units','Feet');
  url.searchParams.set('includeDate','false');
  for (let attempt=0; attempt<4; attempt++) {
    const res = await fetch(url, { headers: { 'User-Agent': 'RedRiverGorgeHiker-route-profile/1.0' } });
    if (res.ok) {
      const data = await res.json();
      const value = Number(data.value ?? data.USGS_Elevation_Point_Query_Service?.Elevation_Query?.Elevation);
      if (Number.isFinite(value)) return value;
    }
    await new Promise((resolve) => setTimeout(resolve, 400 * (attempt + 1)));
  }
  throw new Error(`EPQS failed at ${lat},${lon}`);
};

const elevations = [];
for (let i=0; i<coords.length; i+=5) {
  const batch = coords.slice(i,i+5);
  elevations.push(...await Promise.all(batch.map(query)));
}

const raw = [];
let distance = 0;
coords.forEach((coord,index) => {
  if (index) distance += haversineMiles(coords[index-1],coord);
  raw.push({ distanceMi: Number(distance.toFixed(4)), elevationFt: elevations[index] });
});

const smooth = raw.map((sample,index) => {
  const start = Math.max(0,index-2);
  const end = Math.min(raw.length,index+3);
  const avg = raw.slice(start,end).reduce((sum,item) => sum+item.elevationFt,0)/(end-start);
  return { distanceMi: sample.distanceMi, elevationFt: Math.round(avg) };
});

let ascent=0, descent=0;
for (let i=1;i<smooth.length;i++) {
  const delta=smooth[i].elevationFt-smooth[i-1].elevationFt;
  if (delta>0) ascent+=delta;
  if (delta<0) descent-=delta;
}
const vals=smooth.map((s)=>s.elevationFt);
const artifact={
  routeId: route.properties.routeId,
  geometryVersion: route.properties.version,
  source: {
    id: 'usgs-3dep-epqs',
    name: 'USGS 3DEP Elevation Point Query Service',
    endpoint: 'https://epqs.nationalmap.gov/v1/json',
    units: 'international feet',
    wkid: 4326
  },
  method: {
    description: 'Elevation queried at every approved web-geometry track point from USGS 3DEP EPQS. Display/profile statistics use a centered five-point moving average (shorter window at the ends). Horizontal coordinates are not altered.',
    queryPointCount: coords.length,
    smoothing: 'centered-five-point-moving-average',
    horizontalGeometryChanged: false
  },
  stats: {
    minElevationFt: Math.min(...vals),
    maxElevationFt: Math.max(...vals),
    ascentFt: Math.round(ascent),
    descentFt: Math.round(descent),
    profileDistanceMi: smooth[smooth.length-1].distanceMi
  },
  samples: smooth
};
await fs.mkdir(path.dirname(outputPath),{recursive:true});
await fs.writeFile(outputPath,JSON.stringify(artifact,null,2)+'\n');
console.log(JSON.stringify(artifact,null,2));
