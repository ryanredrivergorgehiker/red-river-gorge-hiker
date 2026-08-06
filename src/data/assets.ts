export interface AssetManifestEntry { catalogId: string; approvedSourceFilename: string; generatedDimensions: readonly number[]; formats: readonly ('avif'|'webp')[]; fileHashes: readonly string[]; generationDate: string|null; watermarkConfirmed: boolean; }
// Approved sources were unavailable on 2026-08-06. Entries remain intentionally ungenerated.
export const assetManifest: readonly AssetManifestEntry[] = [];
