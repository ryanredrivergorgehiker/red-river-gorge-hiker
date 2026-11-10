import { readFile, readdir, appendFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { requireValue, canonicalSHA, sha256, decodeRecord, validateOwner, validateCatalogs,
  validateIndex, IDS } from './rrgh-final-catalog-contract.mjs';
import { ReadBudget, ProtectedReader } from './rrgh-final-catalog-read.mjs';
import { activateCatalogs, rollbackCatalogs, markDeliveryVerified,
  claimDeliveryAllowance, verifyDeliveryClaim } from './rrgh-final-catalog-publish.mjs';
import { verifyDelivery } from './rrgh-final-catalog-smoke.mjs';

const REPO = 'ryanredrivergorgehiker/red-river-gorge-hiker';
const BRANCH = 'lane20/offline-production-preflight-20261029';
const REQUEST = 'operations/rrgh-final-catalog-request.json';
const PROJECT = 'rrgh-nonproduction';
const SA = 'github-deploy@rrgh-nonproduction.iam.gserviceaccount.com';
const CODE = '.github/automation/catalog';
export async function codeDigest(root = '.') {
  const names = (await readdir(root + '/' + CODE)).filter(n => n.endsWith('.mjs')).map(n => CODE + '/' + n);
  names.push('.github/workflows/rrgh-final-catalog.yml');names.sort();
  const entries = [];
  for (const path of names) entries.push({ path, sha256: sha256(await readFile(root + '/' + path)) });
  return canonicalSHA(entries);
}

export async function main(mode) {
  requireValue(['activate', 'verify', 'rollback'].includes(mode), 'Unknown final catalog action');
  requireValue(process.env.GITHUB_REPOSITORY === REPO && process.env.GITHUB_ACTOR === 'ryanredrivergorgehiker' &&
    process.env.GITHUB_EVENT_NAME === 'push' && process.env.GITHUB_REF === 'refs/heads/backend/phase-3-nonprod' &&
    process.env.GITHUB_RUN_ATTEMPT === '1' && /^[1-9][0-9]*$/.test(process.env.GITHUB_RUN_ID || ''),
    'Final catalog requires a fresh owner push on the existing nonproduction branch');
  const raw = await readFile(REQUEST);requireValue(raw.length <= 16384, 'Catalog request exceeds bound');
  const request = JSON.parse(raw), { requestSHA256, ...body } = request;
  requireValue(canonicalSHA(body) === requestSHA256 && request.authorizedBy === 'ryanredrivergorgehiker' &&
    request.projectId === PROJECT && request.action === 'activate-and-verify' && request.automaticRollback === true &&
    request.codeSHA256 === await codeDigest(), 'Owner request or reviewed catalog code changed');
  const runID = Number(process.env.GITHUB_RUN_ID), uid = 'rrgh-final-map-smoke-' + runID;
  const meta = { runID, releaseId: request.authoritySHA256.slice(0, 16) + '-' + runID,
    requestSHA256, catalogCandidates: request.catalogCandidates, verifiedCheckpoint: request.verifiedCheckpoint };
  const requireBackend = createRequire(pathToFileURL(process.cwd() + '/backend/functions/package.json'));
  // Resolve only the repository's existing, pinned nonproduction dependencies.
  const { initializeApp, applicationDefault } = requireBackend('firebase-admin/app');
  const { getFirestore, Timestamp } = requireBackend('firebase-admin/firestore');
  const { getAuth } = requireBackend('firebase-admin/auth');
  const app = initializeApp({ credential: applicationDefault(), projectId: PROJECT, serviceAccountId: SA });
  const db = getFirestore(app), auth = getAuth(app);
  let createdUser = false;
  async function cleanup() {
    let user;
    try { user = await auth.getUser(uid); } catch (error) { if (error.code === 'auth/user-not-found') return;throw error; }
    requireValue(user.customClaims?.rrghFinalMapRunID === runID ||
      user.displayName === 'RRGH final validation ' + runID, 'Cleanup cannot touch another account');
    const account = db.collection('accounts').doc(uid), collections = await account.listCollections();
    requireValue(collections.length <= 8, 'Synthetic account collection bound exceeded');
    for (const collection of collections) {
      const docs = await collection.limit(101).get();requireValue(docs.size <= 100, 'Synthetic account cleanup bound exceeded');
      if (!docs.empty) { const batch = db.batch();for (const doc of docs.docs) batch.delete(doc.ref);await batch.commit(); }
    }
    const capabilities = await db.collection('packageCapabilities').where('uid', '==', uid).limit(201).get();
    requireValue(capabilities.size <= 200, 'Synthetic capability cleanup bound exceeded');
    const batch = db.batch();for (const doc of capabilities.docs) batch.delete(doc.ref);
    batch.delete(account);await batch.commit();await auth.deleteUser(uid);
  }
  if (mode === 'rollback') {
    const result = await rollbackCatalogs(db, meta, Timestamp.now());await cleanup();
    console.log(JSON.stringify(result));return result;
  }
  const github = new ReadBudget({ bytes: 8 * 1024 * 1024, requests: 16 });
  async function gh(path) {
    const { bytes } = await github.request('https://api.github.com/repos/' + REPO + '/' + path, {
      maximum: 1048576, headers: { authorization: 'Bearer ' + process.env.GH_TOKEN,
        accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' } });
    return JSON.parse(bytes.toString('utf8'));
  }
  async function owner() {
    const file = await gh('contents/.github/automation/rrgh-controller-state.json?ref=' + encodeURIComponent(BRANCH));
    requireValue(file.encoding === 'base64' && file.size <= 524288, 'Unexpected controller state envelope');
    const state = JSON.parse(Buffer.from(file.content, 'base64'));
    const run = await gh('actions/runs/' + state.runID), result = await gh('actions/runs/' + state.runID + '/jobs?per_page=100');
    requireValue(result.total_count === result.jobs.length && result.jobs.length <= 100, 'Incomplete package workflow jobs');
    validateOwner(state, request, run, result.jobs);return state;
  }
  await owner();
  if (mode === 'activate') await claimDeliveryAllowance(db, meta, Timestamp.now());
  else await verifyDeliveryClaim(db, meta);
  // Separate fresh jobs have disjoint prepaid bounds; their sum is exactly
  // the retained one-GiB allowance. Proxy ranges count both GCS metadata and
  // object reads, plus all eight backend document reads. The bounded catalog,
  // backup, finalization, rollback and cleanup paths reserve another 3,800
  // direct Firestore operations (including failed attempts, no refunds).
  const budget = new ReadBudget(mode === 'activate' ?
    { bytes: 16 * 1024 * 1024, requests: 225, storageRequests: 225, firestoreOperations: 0 } :
    { bytes: 1008 * 1024 * 1024, requests: 1000, storageRequests: 1775, firestoreOperations: 6200 });
  let token, tokenTime = 0;
  const reader = new ProtectedReader(budget, async () => {
    if (!token || Date.now() - tokenTime > 240000) {
      token = execFileSync('gcloud', ['auth', 'print-access-token'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
      requireValue(token.length > 32, 'No federated read token');tokenTime = Date.now();
    }
    return token;
  });
  const document = decodeRecord(await reader.read(request.catalogCandidates), request.catalogCandidates);
  const checkpoint = decodeRecord(await reader.read(request.verifiedCheckpoint), request.verifiedCheckpoint);
  validateCatalogs(document, checkpoint, request);
  for (const candidate of document.catalogs) {
    if (mode === 'activate') await reader.metadata(candidate);
    if (Object.values(IDS).includes(candidate.packageId)) {
      const ref = { key: candidate.objectName, generation: candidate.objectGeneration,
        sha256: candidate.sha256, bytes: candidate.byteCount };
      validateIndex(JSON.parse(await reader.read(ref)), candidate, document.catalogs);
    }
  }
  if (mode === 'activate') {
    await owner();const result = await activateCatalogs(db, document, meta, Timestamp.now());
    console.log(JSON.stringify({ ...result, readBudget: budget.summary() }));return result;
  }
  let report;
  try {
    // Every run receives a new isolated test identity; no existing account is reset.
    try { await auth.getUser(uid);throw new Error('Synthetic identity already exists'); }
    catch (error) { if (error.code !== 'auth/user-not-found') throw error; }
    requireValue(!(await db.collection('accounts').doc(uid).get()).exists, 'Synthetic account already exists');
    await auth.createUser({ uid, displayName: 'RRGH final validation ' + runID });createdUser = true;
    await auth.setCustomUserClaims(uid, { rrghFinalMapRunID: runID });
    const custom = await auth.createCustomToken(uid, { purpose: 'rrgh-final-map-delivery-validation' });
    const { bytes } = await budget.request('https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=' +
      encodeURIComponent(process.env.FIREBASE_API_KEY), { maximum: 16384, method: 'POST',
      headers: { 'content-type': 'application/json' }, body: JSON.stringify({ token: custom, returnSecureToken: true }) });
    const session = JSON.parse(bytes.toString('utf8'));
    requireValue(session.localId === uid && typeof session.idToken === 'string', 'Synthetic sign-in failed');
    const { verifyOfflineLeaseToken } = await import(pathToFileURL(process.cwd() + '/backend/functions/src/offlineLease.js'));
    report = await verifyDelivery({ budget, document, request, functionUrl: process.env.RRGH_FUNCTION_URL,
      idToken: session.idToken, uid, verifyLease: verifyOfflineLeaseToken,
      verifyCurrentObject: candidate => reader.metadata(candidate) });
  } finally { if (createdUser) await cleanup(); }
  await owner();const result = await markDeliveryVerified(db, meta, report, Timestamp.now());
  console.log(JSON.stringify({ ...result, verification: report }));
  if (process.env.GITHUB_STEP_SUMMARY) await appendFile(process.env.GITHUB_STEP_SUMMARY,
    'All 278,278 raster positions, all three authenticated regional bundles, and both required Day Hike downloads passed server-side validation.\n\n' +
    'Ready for physical iPhone testing; physical iPhone testing has not been performed.\n');
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv[2]).catch(error => { console.error('FINAL_CATALOG_STOP: ' + error.message);process.exitCode = 1; });
}
