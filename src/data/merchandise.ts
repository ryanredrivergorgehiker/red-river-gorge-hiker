export const MERCHANDISE_VERIFICATION_DATE = '2026-08-09' as const;

export interface MerchandiseProduct {
  slug: string;
  title: string;
  priceLabel: string;
  specification: string;
  optionNote?: string;
  fineArtAmericaUrl: string;
  image: {
    avif: string;
    width: number;
    height: number;
    alt: string;
  };
  lastVerified: typeof MERCHANDISE_VERIFICATION_DATE;
}

const assetBase = 'assets/merchandise/' as const;

export const merchandiseProducts: readonly MerchandiseProduct[] = [
  {
    slug: 'greeting-cards',
    title: 'Greeting Cards',
    priceLabel: '$30',
    specification: 'Pack of 10',
    optionNote: 'Optional buyer-entered inside message available during ordering.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=greeting-card',
    image: {
      avif: `${assetBase}rrgh-merch-greeting-card-3837d305.avif`,
      width: 420,
      height: 280,
      alt: 'Red River Gorge Hiker logo greeting card displayed as a folded green card mockup.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'throw-pillow',
    title: 'Throw Pillow',
    priceLabel: 'From $19',
    specification: '14 × 14 inches',
    optionNote: 'Without insert $19 · With insert $24.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=throw-pillow',
    image: {
      avif: `${assetBase}rrgh-merch-throw-pillow-434f2955.avif`,
      width: 420,
      height: 315,
      alt: 'Green Red River Gorge Hiker logo throw pillow on a light-colored sofa.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'tote-bag',
    title: 'Tote Bag',
    priceLabel: '$23.50',
    specification: '18 × 18 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tote-bag',
    image: {
      avif: `${assetBase}rrgh-merch-tote-bag-d6edba01.avif`,
      width: 336,
      height: 420,
      alt: 'Person carrying a green Red River Gorge Hiker logo tote bag outdoors.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'bath-towel',
    title: 'Bath Towel',
    priceLabel: '$32.50',
    specification: '32 × 64 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel',
    image: {
      avif: `${assetBase}rrgh-merch-towel-bath-7b9638b5.avif`,
      width: 336,
      height: 420,
      alt: 'Green Red River Gorge Hiker logo bath towel hanging on a bathroom towel bar.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'beach-towel',
    title: 'Beach Towel',
    priceLabel: '$32.50',
    specification: '32 × 64 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=beach-towel',
    image: {
      avif: `${assetBase}rrgh-merch-towel-beach-61e11fec.avif`,
      width: 256,
      height: 320,
      alt: 'Green Red River Gorge Hiker logo beach towel spread on sand beside the ocean.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'coffee-mug',
    title: 'Coffee Mug',
    priceLabel: '$16',
    specification: 'Large 15 oz. · White',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=coffee-mug-large',
    image: {
      avif: `${assetBase}rrgh-merch-coffee-mug-ef4b0724.avif`,
      width: 280,
      height: 420,
      alt: 'White 15-ounce coffee mug printed with the Red River Gorge Hiker logo.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'spiral-notebook',
    title: 'Spiral Notebook',
    priceLabel: '$16',
    specification: '6 × 8 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=spiral-notebook',
    image: {
      avif: `${assetBase}rrgh-merch-spiral-notebook-8ee997a0.avif`,
      width: 336,
      height: 420,
      alt: 'Green spiral notebook with the Red River Gorge Hiker logo being held and written in.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'sticker',
    title: 'Sticker',
    priceLabel: '$3.50',
    specification: '3 × 3 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=sticker',
    image: {
      avif: `${assetBase}rrgh-merch-sticker-675366d4.avif`,
      width: 413,
      height: 420,
      alt: 'Red River Gorge Hiker logo sticker applied to the rear of a vehicle.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'ornament',
    title: 'Ornament',
    priceLabel: '$9.50',
    specification: 'Red River Gorge Hiker logo ornament',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=ornament',
    image: {
      avif: `${assetBase}rrgh-merch-ornament-31f4a6e1.avif`,
      width: 240,
      height: 320,
      alt: 'Green Red River Gorge Hiker logo ornament hanging on an evergreen Christmas tree.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'fleece-sherpa-blanket',
    title: 'Fleece / Sherpa Blanket',
    priceLabel: 'From $45.50',
    specification: '50 × 60 inches',
    optionNote: 'Plush Fleece $45.50 · Sherpa Fleece $48.50.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=fleece-blanket',
    image: {
      avif: `${assetBase}rrgh-merch-fleece-blanket-277ccd05.avif`,
      width: 336,
      height: 420,
      alt: 'Person wrapped in a green Red River Gorge Hiker logo fleece blanket beside a fireplace.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'tshirt-chest-logo',
    title: 'T-Shirt — Chest Logo',
    priceLabel: 'From $25',
    specification: 'Men’s T-Shirt · Charcoal',
    optionNote: 'Sizes below 2XL verified at $25 · 2XL verified at $28.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-chest-29a80851.avif`,
      width: 420,
      height: 420,
      alt: 'Charcoal T-shirt with a large Red River Gorge Hiker logo centered on the chest.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'tshirt-pocket-logo',
    title: 'T-Shirt — Pocket Logo',
    priceLabel: 'From $25',
    specification: 'Men’s T-Shirt · Charcoal',
    optionNote: 'Select the Pocket design location on Fine Art America. Sizes below 2XL verified at $25 · 2XL at $28.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-pocket-dedbd635.avif`,
      width: 420,
      height: 420,
      alt: 'Charcoal T-shirt with a small Red River Gorge Hiker logo at the pocket position.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'zip-pouch',
    title: 'Zip Pouch',
    priceLabel: 'From $22',
    specification: 'Medium · 9.5 × 6 inches',
    optionNote: 'Regular Bottom $22 · Optional T-style Bottom $22.50.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=pouch',
    image: {
      avif: `${assetBase}rrgh-merch-zip-pouch-54dbc251.avif`,
      width: 336,
      height: 420,
      alt: 'Green Red River Gorge Hiker logo zip pouch held at waist height.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  }
] as const;
