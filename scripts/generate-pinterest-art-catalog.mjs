import fs from 'node:fs/promises';
import path from 'node:path';

const SITE_ROOT = 'https://redrivergorgehiker.com';
const STORE_ROOT = 'https://store.redrivergorgehiker.com';
const DEFAULT_OUTPUT_DIR = 'public/feeds';

const photographs = [
  {
    catalogId: 'RRGH-0001',
    title: 'Double Rainbow at Eagle’s Point Buttress',
    storeBase: `${STORE_ROOT}/featured/double-rainbow-at-eagles-point-buttress-ryan-d-lewis.html`,
    imageFilename: 'RRGH-0001-Double_Rainbow_at_Eagles_Point_Buttress-SOCIAL-WM.jpg',
    altText: 'Double rainbow above foggy forested ridges, photographed from Eagle’s Point Buttress Overlook after a summer storm.'
  },
  {
    catalogId: 'RRGH-0004',
    title: 'Winter at Red-byrd Arch',
    storeBase: `${STORE_ROOT}/featured/winter-at-red-byrd-arch-ryan-d-lewis.html`,
    imageFilename: 'RRGH-0004-Winter_at_Red-byrd_Arch-SOCIAL-WM.jpg',
    altText: 'Large layered ice column beneath the sandstone at Red-byrd Arch, surrounded by snow-covered rocks and winter forest.'
  },
  {
    catalogId: 'RRGH-0005',
    title: 'Sunrise at Eagle’s Nest',
    storeBase: `${STORE_ROOT}/featured/sunrise-at-eagles-nest-ryan-d-lewis.html`,
    imageFilename: 'RRGH-0005-Sunrise_at_Eagles_Nest-SOCIAL-WM.jpg',
    altText: 'Vivid orange sunrise beside the sandstone at Eagle’s Nest, overlooking forested ridges and a river in the Red River Gorge.'
  },
  {
    catalogId: 'RRGH-0002',
    title: 'Dog Fork Falls in Winter',
    storeBase: `${STORE_ROOT}/featured/dog-fork-falls-in-winter-ryan-d-lewis.html`,
    imageFilename: 'RRGH-0002-Dog_Fork_Falls_in_Winter-SOCIAL-WM.jpg',
    altText: 'Dog Fork Falls surrounded by long icicles, snow-covered sandstone, flowing water, and rhododendron in winter.'
  },
  {
    catalogId: 'RRGH-0007',
    title: 'Ice at West of Copperas Pillar',
    storeBase: `${STORE_ROOT}/featured/ice-at-west-of-copperas-pillar-ryan-d-lewis.html`,
    imageFilename: 'RRGH-0007-Ice_at_West_of_Copperas_Pillar-SOCIAL-WM.jpg',
    altText: 'Long icicles hanging beneath sandstone beside West of Copperas Pillar, surrounded by snow, rhododendron, and winter forest.'
  },
  {
    catalogId: 'RRGH-0003',
    title: 'Splatter Falls',
    storeBase: `${STORE_ROOT}/featured/splatter-falls-ryan-d-lewis.html`,
    imageFilename: 'RRGH-0003-Splatter_Falls-SOCIAL-WM.jpg',
    altText: 'Splatter Falls descending through four sandstone drops into an amber pool in the Red River Gorge.'
  }
];

const wallArtFormats = [
  { key: 'ART-PRINT', label: 'Art Print', product: 'art-print', taxonomy: 'Photography > Wall Art > Art Prints' },
  { key: 'CANVAS-PRINT', label: 'Canvas Print', product: 'canvas-print', taxonomy: 'Photography > Wall Art > Canvas Prints' },
  { key: 'FRAMED-PRINT', label: 'Framed Print', product: 'framed-print', taxonomy: 'Photography > Wall Art > Framed Prints' },
  { key: 'METAL-PRINT', label: 'Metal Print', product: 'metal-print', taxonomy: 'Photography > Wall Art > Metal Prints' },
  { key: 'ACRYLIC-PRINT', label: 'Acrylic Print', product: 'acrylic-print', taxonomy: 'Photography > Wall Art > Acrylic Prints' },
  { key: 'WOOD-PRINT', label: 'Wood Print', product: 'wood-print', taxonomy: 'Photography > Wall Art > Wood Prints' },
  { key: 'POSTER', label: 'Poster', product: 'poster', taxonomy: 'Photography > Wall Art > Posters' }
];

const puzzleIds = new Set(['RRGH-0004', 'RRGH-0005', 'RRGH-0007']);
const greetingCard = {
  catalogId: 'RRGH-0001-GREETING-CARD',
  photoCatalogId: 'RRGH-0001',
  link: `${STORE_ROOT}/featured/double-rainbow-at-eagles-point-ryan-d-lewis.html?product=greeting-card`,
  taxonomy: 'Photography > Stationery > Greeting Cards'
};

const htmlEntityMap = new Map([
  ['&nbsp;', ' '], ['&amp;', '&'], ['&quot;', '"'], ['&#39;', "'"], ['&apos;', "'"], ['&lt;', '<'], ['&gt;', '>']
]);

function decodeHtml(text = '') {
  return text
    .replace(/&nbsp;|&amp;|&quot;|&#39;|&apos;|&lt;|&gt;/g, (m) => htmlEntityMap.get(m) ?? m)
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function csv(value) {
  const s = String(value ?? '');
  return `"${s.replaceAll('"', '""')}"`;
}

function findJsonLdProducts(node, out = []) {
  if (!node) return out;
  if (Array.isArray(node)) {
    for (const item of node) findJsonLdProducts(item, out);
    return out;
  }
  if (typeof node !== 'object') return out;
  const type = node['@type'];
  if (type === 'Product' || (Array.isArray(type) && type.includes('Product'))) out.push(node);
  for (const value of Object.values(node)) findJsonLdProducts(value, out);
  return out;
}

async function fetchWithRetry(url, options = {}, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const response = await fetch(url, {
        redirect: 'follow',
        ...options,
        headers: {
          'user-agent': 'Mozilla/5.0 (compatible; RedRiverGorgeHiker-PinterestCatalog/1.0; +https://redrivergorgehiker.com)',
          'accept-language': 'en-US,en;q=0.9',
          ...(options.headers ?? {})
        }
      });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response;
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, 1000 * attempt));
    }
  }
  throw new Error(`Failed after ${attempts} attempts: ${url}: ${lastError}`);
}

function jpegDimensions(buffer) {
  if (buffer[0] !== 0xff || buffer[1] !== 0xd8) throw new Error('Not a JPEG');
  let offset = 2;
  while (offset < buffer.length) {
    if (buffer[offset] !== 0xff) { offset += 1; continue; }
    const marker = buffer[offset + 1];
    offset += 2;
    if (marker === 0xd8 || marker === 0xd9) continue;
    if (offset + 2 > buffer.length) break;
    const length = buffer.readUInt16BE(offset);
    const sof = [0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker);
    if (sof) {
      return { height: buffer.readUInt16BE(offset + 3), width: buffer.readUInt16BE(offset + 5) };
    }
    if (length < 2) break;
    offset += length;
  }
  throw new Error('Could not determine JPEG dimensions');
}

async function verifyApprovedImages() {
  const cache = new Map();
  for (const photo of photographs) {
    const url = `${SITE_ROOT}/assets/social/${encodeURIComponent(photo.imageFilename)}`;
    const response = await fetchWithRetry(url);
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.toLowerCase().includes('image/jpeg')) throw new Error(`Unexpected image content type for ${url}: ${contentType}`);
    const buffer = Buffer.from(await response.arrayBuffer());
    const dimensions = jpegDimensions(buffer);
    if (dimensions.width < 1000 || dimensions.height < 1500) {
      throw new Error(`Pinterest image minimum not met for ${photo.catalogId}: ${dimensions.width}x${dimensions.height}`);
    }
    cache.set(photo.catalogId, { url, ...dimensions, bytes: buffer.length });
    console.log(`IMAGE PASS ${photo.catalogId}: ${dimensions.width}x${dimensions.height}, ${buffer.length} bytes`);
  }
  return cache;
}

async function fetchProduct(link) {
  const response = await fetchWithRetry(link);
  const html = await response.text();
  const scripts = [...html.matchAll(/<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]);
  const products = [];
  for (const raw of scripts) {
    try {
      findJsonLdProducts(JSON.parse(raw), products);
    } catch {
      // Ignore non-JSON script blocks; the product page normally exposes a valid Product block.
    }
  }
  const product = products.find((p) => p.offers?.price && p.offers?.priceCurrency) ?? products[0];
  if (!product) throw new Error(`No Product JSON-LD found: ${link}`);
  const offer = Array.isArray(product.offers) ? product.offers[0] : product.offers;
  const currency = String(offer?.priceCurrency ?? '').toUpperCase();
  const price = Number(offer?.price);
  const availabilityUrl = String(offer?.availability ?? '');
  if (currency !== 'USD') throw new Error(`Expected USD price for ${link}, got ${currency || 'none'}`);
  if (!Number.isFinite(price) || price <= 0) throw new Error(`Invalid price for ${link}: ${offer?.price}`);
  let availability;
  if (/InStock$/i.test(availabilityUrl)) availability = 'in stock';
  else if (/OutOfStock$/i.test(availabilityUrl)) availability = 'out of stock';
  else if (/PreOrder$/i.test(availabilityUrl)) availability = 'preorder';
  else throw new Error(`Unsupported availability for ${link}: ${availabilityUrl}`);
  const canonicalLink = String(product.url || offer?.url || link).replaceAll('&amp;', '&');
  return {
    sourceLink: link,
    link: canonicalLink,
    title: decodeHtml(product.name),
    description: decodeHtml(product.description),
    price,
    priceCurrency: currency,
    availability,
    sku: decodeHtml(product.sku ?? ''),
    brand: decodeHtml(product.brand?.name ?? ''),
    sourceProductImage: Array.isArray(product.image) ? product.image[0] : (product.image ?? '')
  };
}

function plannedItems() {
  const items = [];
  for (const photo of photographs) {
    for (const format of wallArtFormats) {
      items.push({
        id: `${photo.catalogId}-${format.key}`,
        photoCatalogId: photo.catalogId,
        expectedFormat: format.label,
        sourceLink: `${photo.storeBase}?product=${format.product}`,
        taxonomy: format.taxonomy,
        altText: photo.altText
      });
    }
    if (puzzleIds.has(photo.catalogId)) {
      items.push({
        id: `${photo.catalogId}-PUZZLE`,
        photoCatalogId: photo.catalogId,
        expectedFormat: 'Jigsaw Puzzle',
        sourceLink: `${photo.storeBase}?product=puzzle`,
        taxonomy: 'Photography > Puzzles > Jigsaw Puzzles',
        altText: photo.altText
      });
    }
  }
  const photo = photographs.find((p) => p.catalogId === greetingCard.photoCatalogId);
  items.push({
    id: greetingCard.catalogId,
    photoCatalogId: greetingCard.photoCatalogId,
    expectedFormat: 'Greeting Card',
    sourceLink: greetingCard.link,
    taxonomy: greetingCard.taxonomy,
    altText: photo.altText
  });
  return items;
}

async function main() {
  const outputDirArgIndex = process.argv.indexOf('--output-dir');
  const outputDir = outputDirArgIndex >= 0 ? process.argv[outputDirArgIndex + 1] : DEFAULT_OUTPUT_DIR;
  if (!outputDir) throw new Error('--output-dir requires a value');

  const imageEvidence = await verifyApprovedImages();
  const plan = plannedItems();
  if (plan.length !== 46) throw new Error(`Stage 1 control failure: expected 46 items, got ${plan.length}`);

  const rows = [];
  for (let i = 0; i < plan.length; i++) {
    const planned = plan[i];
    const product = await fetchProduct(planned.sourceLink);
    if (!product.title.toLowerCase().includes(planned.expectedFormat.toLowerCase())) {
      throw new Error(`Product-title mismatch for ${planned.id}: expected ${planned.expectedFormat}, got ${product.title}`);
    }
    const image = imageEvidence.get(planned.photoCatalogId);
    rows.push({
      id: planned.id,
      title: product.title,
      description: product.description,
      link: product.link,
      image_link: image.url,
      price: `${product.price.toFixed(2)} USD`,
      availability: product.availability,
      product_type: planned.taxonomy,
      alt_text: planned.altText,
      source_sku: product.sku,
      source_product_image: product.sourceProductImage,
      approved_image_width: image.width,
      approved_image_height: image.height
    });
    console.log(`PRODUCT PASS ${String(i + 1).padStart(2, '0')}/46 ${planned.id}: ${product.title} | ${product.price.toFixed(2)} USD | ${product.availability}`);
  }

  await fs.mkdir(outputDir, { recursive: true });
  const columns = ['id','title','description','link','image_link','price','availability','product_type','alt_text'];
  const csvText = [columns.map(csv).join(','), ...rows.map((row) => columns.map((c) => csv(row[c])).join(','))].join('\n') + '\n';
  const csvPath = path.join(outputDir, 'pinterest-art-catalog.csv');
  await fs.writeFile(csvPath, csvText, 'utf8');

  const manifest = {
    generatedAt: new Date().toISOString(),
    stage: 'Stage 1 — photography commerce only',
    itemCount: rows.length,
    itemGrouping: 'Each of the 46 catalog entries is a standalone product; item_group_id is intentionally omitted.',
    transactionAuthority: STORE_ROOT,
    imageAuthority: `${SITE_ROOT}/assets/social/`,
    noGear: true,
    paidCampaignChanged: false,
    rows
  };
  const manifestPath = path.join(outputDir, 'pinterest-art-catalog-manifest.json');
  await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n', 'utf8');

  console.log(`CATALOG PASS: ${rows.length} rows`);
  console.log(`CSV: ${csvPath}`);
  console.log(`MANIFEST: ${manifestPath}`);
}

main().catch((error) => {
  console.error('CATALOG BUILD FAILED');
  console.error(error?.stack || error);
  process.exit(1);
});
