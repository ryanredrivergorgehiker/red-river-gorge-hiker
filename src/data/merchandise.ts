export const MERCHANDISE_VERIFICATION_DATE = '2026-08-09' as const;

export interface MerchandiseProduct {
  slug: string;
  title: string;
  description: string;
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
    slug: 'tshirt-chest-logo',
    title: 'T-Shirt — Chest Logo',
    description: 'Charcoal Red River Gorge Hiker T-shirt with the logo centered on the chest, inspired by Kentucky’s Red River Gorge and Clifty Wilderness.',
    priceLabel: 'From $25',
    specification: 'Men’s T-Shirt · Charcoal',
    optionNote: 'Sizes below 2XL verified at $25 · 2XL verified at $28.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-chest-70ec579b.avif`,
      width: 800,
      height: 1000,
      alt: 'Charcoal T-shirt with a large Red River Gorge Hiker logo centered on the chest.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'sticker',
    title: 'Sticker',
    description: 'A 3 × 3-inch Red River Gorge Hiker logo sticker for hikers and fans of Kentucky’s Red River Gorge.',
    priceLabel: '$3.50',
    specification: '3 × 3 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=sticker',
    image: {
      avif: `${assetBase}rrgh-merch-sticker-218cc04a.avif`,
      width: 983,
      height: 1000,
      alt: 'Red River Gorge Hiker logo sticker applied to the rear of a vehicle.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'tote-bag',
    title: 'Tote Bag',
    description: 'An 18 × 18-inch green tote bag featuring the Red River Gorge Hiker logo.',
    priceLabel: '$23.50',
    specification: '18 × 18 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tote-bag',
    image: {
      avif: `${assetBase}rrgh-merch-tote-bag-bc2e6737.avif`,
      width: 800,
      height: 1000,
      alt: 'Person carrying a green Red River Gorge Hiker logo tote bag outdoors.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'coffee-mug',
    title: 'Coffee Mug',
    description: 'A large white 15-ounce coffee mug printed with the Red River Gorge Hiker logo.',
    priceLabel: '$16',
    specification: 'Large 15 oz. · White',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=coffee-mug-large',
    image: {
      avif: `${assetBase}rrgh-merch-coffee-mug-0d15378a.avif`,
      width: 800,
      height: 1000,
      alt: 'White 15-ounce coffee mug printed with the Red River Gorge Hiker logo.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'tshirt-pocket-logo',
    title: 'T-Shirt — Pocket Logo',
    description: 'Charcoal Red River Gorge Hiker T-shirt with a small logo at the pocket position.',
    priceLabel: 'From $25',
    specification: 'Men’s T-Shirt · Charcoal',
    optionNote: 'Select the Pocket design location on Fine Art America. Sizes below 2XL verified at $25 · 2XL at $28.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-pocket-305a009a.avif`,
      width: 800,
      height: 1000,
      alt: 'Charcoal T-shirt with a small Red River Gorge Hiker logo at the pocket position.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'throw-pillow',
    title: 'Throw Pillow',
    description: 'A 14 × 14-inch green throw pillow featuring the Red River Gorge Hiker logo, available with or without an insert.',
    priceLabel: 'From $19',
    specification: '14 × 14 inches',
    optionNote: 'Without insert $19 · With insert $24.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=throw-pillow',
    image: {
      avif: `${assetBase}rrgh-merch-throw-pillow-50251954.avif`,
      width: 1000,
      height: 750,
      alt: 'Green Red River Gorge Hiker logo throw pillow on a light-colored sofa.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'fleece-sherpa-blanket',
    title: 'Fleece / Sherpa Blanket',
    description: 'A 50 × 60-inch Red River Gorge Hiker logo blanket available in Plush Fleece or Sherpa Fleece.',
    priceLabel: 'From $45.50',
    specification: '50 × 60 inches',
    optionNote: 'Plush Fleece $45.50 · Sherpa Fleece $48.50.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=fleece-blanket',
    image: {
      avif: `${assetBase}rrgh-merch-fleece-blanket-c5e93147.avif`,
      width: 800,
      height: 1000,
      alt: 'Person wrapped in a green Red River Gorge Hiker logo fleece blanket beside a fireplace.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'zip-pouch',
    title: 'Zip Pouch',
    description: 'A medium 9.5 × 6-inch green Red River Gorge Hiker logo zip pouch with regular or T-style bottom options.',
    priceLabel: 'From $22',
    specification: 'Medium · 9.5 × 6 inches',
    optionNote: 'Regular Bottom $22 · Optional T-style Bottom $22.50.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=pouch',
    image: {
      avif: `${assetBase}rrgh-merch-zip-pouch-04134418.avif`,
      width: 800,
      height: 1000,
      alt: 'Green Red River Gorge Hiker logo zip pouch held at waist height.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'spiral-notebook',
    title: 'Spiral Notebook',
    description: 'A 6 × 8-inch green spiral notebook featuring the Red River Gorge Hiker logo.',
    priceLabel: '$16',
    specification: '6 × 8 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=spiral-notebook',
    image: {
      avif: `${assetBase}rrgh-merch-spiral-notebook-62906115.avif`,
      width: 800,
      height: 1000,
      alt: 'Green spiral notebook with the Red River Gorge Hiker logo being held and written in.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'bath-towel',
    title: 'Bath Towel',
    description: 'A 32 × 64-inch green bath towel featuring the Red River Gorge Hiker logo.',
    priceLabel: '$32.50',
    specification: '32 × 64 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel',
    image: {
      avif: `${assetBase}rrgh-merch-towel-bath-051a15a3.avif`,
      width: 800,
      height: 1000,
      alt: 'Green Red River Gorge Hiker logo bath towel hanging on a bathroom towel bar.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'beach-towel',
    title: 'Beach Towel',
    description: 'A 32 × 64-inch green beach towel featuring the Red River Gorge Hiker logo.',
    priceLabel: '$32.50',
    specification: '32 × 64 inches',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=beach-towel',
    image: {
      avif: `${assetBase}rrgh-merch-towel-beach-35a77bd5.avif`,
      width: 800,
      height: 1000,
      alt: 'Green Red River Gorge Hiker logo beach towel spread on sand beside the ocean.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'greeting-cards',
    title: 'Greeting Cards',
    description: 'A pack of 10 Red River Gorge Hiker logo greeting cards with an optional buyer-entered inside message.',
    priceLabel: '$30',
    specification: 'Pack of 10',
    optionNote: 'Optional buyer-entered inside message available during ordering.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=greeting-card',
    image: {
      avif: `${assetBase}rrgh-merch-greeting-card-415e37be.avif`,
      width: 1000,
      height: 750,
      alt: 'Red River Gorge Hiker logo greeting card displayed as a folded green card mockup.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'ornament',
    title: 'Ornament',
    description: 'A green Red River Gorge Hiker logo ornament for the holiday season.',
    priceLabel: '$9.50',
    specification: 'Red River Gorge Hiker logo ornament',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=ornament',
    image: {
      avif: `${assetBase}rrgh-merch-ornament-2c0c7784.avif`,
      width: 750,
      height: 1000,
      alt: 'Green Red River Gorge Hiker logo ornament hanging on an evergreen Christmas tree.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  }
] as const;
