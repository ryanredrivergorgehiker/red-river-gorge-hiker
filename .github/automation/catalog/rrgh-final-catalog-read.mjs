import { requireValue, sha256, checkRef, BUCKET } from './rrgh-final-catalog-contract.mjs';

// Precharge every attempt, including unsuccessful responses. No automatic retry.
export class ReadBudget {
  constructor({ bytes, requests, storageRequests = requests * 2, firestoreOperations = requests * 8 }, fetcher = fetch) {
    this.limitBytes = bytes;this.limitRequests = requests;this.bytes = 0;this.requests = 0;this.fetcher = fetcher;
    this.limitStorage = storageRequests;this.limitFirestore = firestoreOperations;
    this.storageRequests = 0;this.firestoreOperations = 0;
  }
  async request(url, { maximum, expectedStatus = 200, storageRequests = 0, firestoreOperations = 0, ...options }) {
    requireValue(Number.isSafeInteger(maximum) && maximum > 0 && maximum <= this.limitBytes - this.bytes &&
      this.requests < this.limitRequests, 'Final delivery read allowance exhausted before request');
    requireValue(Number.isSafeInteger(storageRequests) && storageRequests >= 0 &&
      Number.isSafeInteger(firestoreOperations) && firestoreOperations >= 0 &&
      storageRequests <= this.limitStorage - this.storageRequests &&
      firestoreOperations <= this.limitFirestore - this.firestoreOperations,
      'Final delivery indirect storage or Firestore allowance exhausted before request');
    this.bytes += maximum;this.requests++;
    this.storageRequests += storageRequests;this.firestoreOperations += firestoreOperations;
    const response = await this.fetcher(url, { ...options, redirect: 'error', signal: AbortSignal.timeout(120000) });
    requireValue(response.status === expectedStatus, `Bounded final delivery request failed: HTTP ${response.status}`);
    const length = response.headers.get('content-length');
    if (length !== null) requireValue(/^\d+$/.test(length) && Number(length) <= maximum, 'Response exceeds reserved read bytes');
    const reader = response.body?.getReader();const chunks = [];let total = 0;
    if (reader) {
      try {
        while (true) {
          const { done, value } = await reader.read();if (done) break;
          total += value.length;requireValue(total <= maximum, 'Streaming response exceeds reserved read bytes');
          chunks.push(Buffer.from(value));
        }
      } catch (error) { await reader.cancel().catch(() => {});throw error; }
    }
    return { response, bytes: Buffer.concat(chunks, total) };
  }
  summary() { return { reservedReadBytes: this.bytes, requests: this.requests,
    maxReadBytes: this.limitBytes, maxRequests: this.limitRequests,
    storageRequests: this.storageRequests, maxStorageRequests: this.limitStorage,
    firestoreOperations: this.firestoreOperations, maxFirestoreOperations: this.limitFirestore }; }
}

export class ProtectedReader {
  constructor(budget, token) { this.budget = budget;this.token = token; }
  async read(ref) {
    checkRef(ref);
    const url = `https://storage.googleapis.com/storage/v1/b/${BUCKET}/o/${encodeURIComponent(ref.key)}` +
      `?alt=media&generation=${ref.generation}`;
    const { bytes } = await this.budget.request(url, { maximum: ref.bytes, storageRequests: 1,
      headers: { authorization: 'Bearer ' + await this.token() } });
    requireValue(bytes.length === ref.bytes && sha256(bytes) === ref.sha256, 'Protected delivery record differs from accepted bytes');
    return bytes;
  }
  async metadata(candidate) {
    const ref = { key: candidate.objectName, generation: candidate.objectGeneration,
      bytes: candidate.byteCount, sha256: candidate.sha256 };checkRef(ref, 256000000);
    const url = `https://storage.googleapis.com/storage/v1/b/${BUCKET}/o/${encodeURIComponent(ref.key)}` +
      '?fields=name,bucket,generation,size,metadata,contentType';
    // The existing backend opens the current object at this immutable path.
    // Checking only an older generation could miss a changed current object.
    const { bytes } = await this.budget.request(url, { maximum: 16384, storageRequests: 1,
      headers: { authorization: 'Bearer ' + await this.token() } });
    const value = JSON.parse(bytes.toString('utf8'));
    requireValue(value.name === ref.key && value.bucket === BUCKET && value.generation === ref.generation &&
      value.size === String(ref.bytes) && value.metadata?.['rrgh-sha256'] === ref.sha256 &&
      value.metadata?.['rrgh-package-id'] === candidate.packageId && value.metadata?.['rrgh-version'] === candidate.version,
      'Generation-pinned private object metadata differs from accepted catalog');
    return true;
  }
}
