import rawManifest from '../../asset-manifest.json';

export type ArtworkFormat = 'avif' | 'webp';

export interface ArtworkDerivative {
  publicFilename: string;
  width: number;
  height: number;
  format: ArtworkFormat;
}

export interface ArtworkAsset {
  catalogId: string;
  derivatives: readonly ArtworkDerivative[];
}

interface BrandAsset {
  publicFilename: string;
  width: number;
  height: number;
}

interface QrAsset {
  publicFilename: string;
  destination: string;
}

interface PublicAssetManifest {
  releaseVersion: string;
  artworks: readonly ArtworkAsset[];
  brand: BrandAsset;
  qr: readonly QrAsset[];
}

const manifest = rawManifest as unknown as PublicAssetManifest;

export const assetManifest = manifest.artworks;
export const brandAsset = manifest.brand;
export const qrAssets = manifest.qr;

export function getArtworkAsset(catalogId: string): ArtworkAsset | undefined {
  return assetManifest.find((entry) => entry.catalogId === catalogId);
}
