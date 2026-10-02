import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const ROOT = process.cwd();
const file = path.join(ROOT, 'src', 'data', 'places', 'places.generated.json');
const EXPECTED_SHA = 'e6afebfbbd250eee4de3e0f47db2a91e7ae053fff6659f6fc0d312caf75034b3';
const EXPECTED_SOURCE = '1GcUKlJTy18qP4yGu4n1qhLzy3IkOM-U2M_2LJLYIW-4';
const fail = (message) => { throw new Error(message); };
const bytes = fs.readFileSync(file);
const sha = crypto.createHash('sha256').update(bytes).digest('hex');
if (sha !== EXPECTED_SHA) fail('Places snapshot hash mismatch: ' + sha);
const data = JSON.parse(bytes.toString('utf8'));
if (data?.metadata?.sourceRegisterId !== EXPECTED_SOURCE) fail('Places source register mismatch');
if (data?.metadata?.verificationState !== 'verification-cleared') fail('Places snapshot is not verification-cleared');
const places = data.activePlaces;
const excluded = data.excludedAndSuperseded;
if (!Array.isArray(places) || !Array.isArray(excluded)) fail('Places snapshot arrays missing');
const around = places.filter(p => p.aroundTheGorge);
const hiker = places.filter(p => p.hikerServices);
const dual = places.filter(p => p.aroundTheGorge && p.hikerServices);
const presence = places.filter(p => p.rrghPresence);
const eligible = places.filter(p => p.mapPoiEligible);
const ids = new Set(places.map(p => p.placeId));
const names = new Set(places.map(p => p.publicName));
if (places.length !== 29 || ids.size !== 29 || names.size !== 29) fail('Expected 29 unique active canonical Places');
if (around.length !== 23) fail('Expected 23 Around the Gorge Places');
if (hiker.length !== 10) fail('Expected 10 Hiker Services Places');
if (dual.length !== 4) fail('Expected 4 dual-membership Places');
if (presence.length !== 3) fail('Expected 3 RRGH Presence Places');
if (eligible.length !== 29) fail('Expected 29 map-eligible Places');
if (excluded.length !== 10) fail('Expected 10 excluded/superseded controls');
const aroundCategories = new Set(['Eat & Drink','Things to Do','Local Shops & Stops']);
for (const p of places) {
  if (!/^PLC-\d{3}$/.test(p.placeId)) fail('Invalid Place ID: ' + p.placeId);
  if (!Number.isFinite(p.latitude) || !Number.isFinite(p.longitude)) fail(p.placeId + ': missing verified coordinates');
  if (!p.officialSourceUrl || !p.lastVerified) fail(p.placeId + ': missing source/verification');
  if (p.aroundTheGorge && !aroundCategories.has(p.aroundCategory)) fail(p.placeId + ': invalid Around category');
  if (p.hikerServices && (!Array.isArray(p.hikerServiceTypes) || !p.hikerServiceTypes.length || p.hikerServiceTypes.includes('29'))) fail(p.placeId + ': invalid Hiker Service types');
  if (p.rrghPresence && (!p.rrghPresenceSubtype || p.rrghPresenceSubtype === '29' || !p.relationshipDisclosure || p.relationshipDisclosure === '29')) fail(p.placeId + ': invalid RRGH Presence disclosure');
}
const presenceContract = new Map(presence.map(p => [p.placeId,p.rrghPresenceSubtype]));
for (const [id,subtype] of [['PLC-002','photo-display-sales'],['PLC-009','donated-display'],['PLC-018','greeting-card-retail']]) {
  if (presenceContract.get(id) !== subtype) fail(id + ': RRGH Presence subtype mismatch');
}
if (places.find(p => p.placeId === 'PLC-021')?.publicName !== 'The Brick at the Red River Gorge') fail('PLC-021 canonical name mismatch');
if (places.find(p => p.placeId === 'PLC-026')?.publicName !== 'Trails Liquor, Souvenir, & General Store') fail('PLC-026 canonical name mismatch');
if (places.find(p => p.placeId === 'PLC-016')?.publicName !== 'Southeast Mountain Guides') fail('PLC-016 canonical name mismatch');
if (places.find(p => p.placeId === 'PLC-025')?.publicName !== 'Park N Save') fail('PLC-025 canonical name mismatch');
const hillTop = places.find(p => p.placeId === 'PLC-010');
if (!hillTop?.nearbyRrghPickEligible || hillTop?.nearbyRouteContext !== 'Motherlode area') fail('Hill Top Pizza Motherlode Nearby RRGH Pick contract mismatch');
for (const x of excluded) if (names.has(x.nameOrCandidate)) fail('Excluded/superseded record became active publicName: ' + x.nameOrCandidate);
console.log('Places contract PASS: 29 active; 23 Around; 10 Hiker Services; 4 dual; 3 RRGH Presence; 29 map POIs; 10 excluded/superseded controls.');
