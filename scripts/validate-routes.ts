import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const sha256=(b:Buffer|string)=>createHash('sha256').update(b).digest('hex');
const gpx=readFileSync('public/downloads/routes/skybridge-arch.gpx');
const geo=readFileSync('public/data/routes/skybridge-arch.geojson');
const expectedGpx='2469c85ebaddd3e701ba6dc8eea3664d90a0667dcd86f2aab43ae1445986830d';
const expectedGeo='123fdb57e1142299f86c714367cc466b70f18fa90cfbaabb92b0d9ced157dc66';
if(sha256(gpx)!==expectedGpx) throw new Error('Approved Skybridge GPX hash mismatch.');
if(sha256(geo)!==expectedGeo) throw new Error('Approved Skybridge GeoJSON hash mismatch.');
const gpxText=gpx.toString('utf8');
if((gpxText.match(/<trkpt\b/g)||[]).length!==100) throw new Error('Approved GPX must contain exactly 100 track points.');
if((gpxText.match(/<wpt\b/g)||[]).length!==2) throw new Error('Approved GPX must contain exactly two public waypoints.');
for(const forbidden of ['<time>','<ele>','Gaia GPS','eagle-nest','Eagle Nest']) {
  if(gpxText.includes(forbidden)) throw new Error(`Forbidden GPX content detected: ${forbidden}`);
}
const fc=JSON.parse(geo.toString('utf8'));
const line=fc.features.filter((f:any)=>f.geometry?.type==='LineString');
const points=fc.features.filter((f:any)=>f.geometry?.type==='Point');
if(line.length!==1 || line[0].geometry.coordinates.length!==100) throw new Error('Approved GeoJSON route geometry mismatch.');
if(points.length!==2) throw new Error('Approved GeoJSON waypoint count mismatch.');
const waypointNames=points.map((f:any)=>f.properties.name).sort().join('|');
if(waypointNames!=='Skybridge Arch|Turnaround Overlook') throw new Error('Approved waypoint inventory mismatch.');
const publicRoots=['public/data/routes','public/downloads/routes','src/data/routes'];
const privateOrWorkingTokens=[
  '1w0Uq5LPJxmVKEQCqJ6SIvdSGOEAnP_lM',
  '1sSGv8HHir_DEwP112Bth99WSnh_IBPKi',
  '1q_mK8GhoqFTOQoGRCXHzG7DTxDIL5Uz1',
  '1tFL9zsZeMCZVhh55dmljYQ2oCgShv0A3',
  '1PaL0N8YX811a7q0n5X7rmvT4DYVil6HK',
  '1UcAecDg8fHKdb1vnEeV7n0I9nRTK-X0m',
  '1J52ye_cbq_m9KscENf36-Tg0K652cuZm',
  '1V8ycSPIPLbHme73yxjiPAD67x6Opqqvj',
  '13QegbAxx4ttNp0YobpsHCFg2Bu1Ez4Gz',
  'RAW Gaia',
  'Intake working'
];
const walk=(dir:string):string[]=>readdirSync(dir,{withFileTypes:true}).flatMap((e)=>e.isDirectory()?walk(join(dir,e.name)):[join(dir,e.name)]);
for(const root of publicRoots){
  for(const file of walk(root)){
    const text=readFileSync(file,'utf8');
    for(const token of privateOrWorkingTokens){
      if(text.includes(token)) throw new Error(`Private/source-only token found in ${file}: ${token}`);
    }
  }
}
const routeMd=readFileSync('src/data/routes/skybridge-arch.md','utf8');
if(!routeMd.includes('publicationStatus: "Approved — Publication Ready"')) throw new Error('Route is not publication-ready.');
if(!routeMd.includes('WP-0001')||!routeMd.includes('WP-0002')) throw new Error('Approved waypoint records missing.');
if(/Class D|Sensitive \/ Withheld/.test(routeMd)) throw new Error('Withheld route data must not enter public collection.');
const layers=readFileSync('src/data/map/layers.ts','utf8');
if(!layers.includes("id: 'parcel-private-property'")||!layers.includes("implementation: 'BLOCKED.")) throw new Error('Parcel layer must remain explicitly blocked.');
if(!layers.includes('Ky_MultiDirectional_Hillshade_WGS84WM')) throw new Error('Approved Kentucky hillshade endpoint missing.');
if(!layers.includes('epqs.nationalmap.gov/v1/json')) throw new Error('Approved USGS 3DEP elevation source missing.');
console.log('Routes & Tracks validation passed: approved artifacts, waypoints, public-data boundary and source registry are intact.');
