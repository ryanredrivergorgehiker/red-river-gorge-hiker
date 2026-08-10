export const MERCHANDISE_VERIFICATION_DATE = '2026-08-10' as const;

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
    title: 'Men’s T-Shirt (Athletic Fit) — Chest Logo',
    description: 'Charcoal athletic-fit men’s Red River Gorge Hiker T-shirt with the logo centered on the chest.',
    priceLabel: 'From $25',
    specification: 'Men’s T-Shirt · Athletic Fit · Chest Logo',
    optionNote: 'Sizes below 2XL verified at $25 · 2XL verified at $28.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt&completeProductSku=artworkid[70456163]-productid[clothing-23]-imagewidth[286]-imageheight[286]-targetx[72]-targety[0]-modelwidth[430]-modelheight[575]-backgroundcolor[5]-orientation[0]-size[3]',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-chest-70ec579b.avif`,
      width: 800,
      height: 1000,
      alt: 'Charcoal athletic-fit men’s T-shirt with a large Red River Gorge Hiker logo centered on the chest.'
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
    slug: 'mens-tshirt-regular-fit',
    title: 'Men’s T-Shirt (Regular Fit)',
    description: 'Regular-fit men’s Red River Gorge Hiker T-shirt with the logo presented on the chest.',
    priceLabel: 'From $23',
    specification: 'Men’s T-Shirt · Regular Fit',
    optionNote: '$23 through XL · $26 at 2XL · $28 at 3XL.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=regular-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-mens-tshirt-regular-4934da22.avif`,
      width: 720,
      height: 900,
      alt: 'Men’s regular-fit Red River Gorge Hiker T-shirt with the logo on the chest.'
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
    slug: 'womens-tshirt',
    title: 'Women’s T-Shirt',
    description: 'Women’s Red River Gorge Hiker T-shirt presented with the logo on the chest.',
    priceLabel: 'From $25',
    specification: 'Women’s T-Shirt · Chest presentation',
    optionNote: '$25 through XL · $28 at 2XL. RedRiverGorgeHiker.com promotes the Chest presentation only.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=womens-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-womens-tshirt-55652f0b.avif`,
      width: 720,
      height: 900,
      alt: 'Women’s Red River Gorge Hiker T-shirt with the logo on the chest.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'sweatshirt',
    title: 'Sweatshirt',
    description: 'Red River Gorge Hiker sweatshirt presented with the logo on the chest.',
    priceLabel: 'From $45',
    specification: 'Sweatshirt · Chest presentation',
    optionNote: '$45 below 2XL · $51 at 2XL · $57 at 3XL. RedRiverGorgeHiker.com promotes the Chest presentation only.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=pull-over-hoodie-sweatshirt',
    image: {
      avif: `${assetBase}rrgh-merch-sweatshirt-427c6025.avif`,
      width: 720,
      height: 900,
      alt: 'Red River Gorge Hiker sweatshirt with the logo on the chest.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'tshirt-pocket-logo',
    title: 'Men’s T-Shirt (Athletic Fit) — Pocket Logo',
    description: 'Charcoal athletic-fit men’s Red River Gorge Hiker T-shirt with a small logo at the pocket position.',
    priceLabel: 'From $25',
    specification: 'Men’s T-Shirt · Athletic Fit · Pocket Logo',
    optionNote: 'Dedicated Pocket presentation. Sizes below 2XL verified at $25 · 2XL verified at $28.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt&completeProductSku=artworkid[70456163]-productid[clothing-23]-imagewidth[430]-imageheight[430]-targetx[0]-targety[0]-modelwidth[430]-modelheight[575]-backgroundcolor[5]-orientation[0]-size[3]-designlocation[pocket]',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-pocket-v3-ad2cb2e6.avif`,
      width: 720,
      height: 900,
      alt: 'Charcoal athletic-fit men’s T-shirt with a small Red River Gorge Hiker logo at the pocket position.'
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
    slug: 'womens-tank-top',
    title: 'Women’s Tank Top',
    description: 'Women’s Red River Gorge Hiker tank top presented with the logo on the chest.',
    priceLabel: 'From $25',
    specification: 'Women’s Tank Top · Chest presentation',
    optionNote: '$25 across the verified sizes. RedRiverGorgeHiker.com promotes the Chest presentation only.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=womens-tank-top',
    image: {
      avif: `${assetBase}rrgh-merch-womens-tank-7fa9ad7b.avif`,
      width: 675,
      height: 900,
      alt: 'Women’s Red River Gorge Hiker tank top with the logo on the chest.'
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
    slug: 'youth-tshirt',
    title: 'Youth T-Shirt',
    description: 'Youth Red River Gorge Hiker T-shirt featuring the logo.',
    priceLabel: 'From $21',
    specification: 'Youth T-Shirt',
    optionNote: '$21 across the verified sizes.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=youth-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-youth-tshirt-13c4358d.avif`,
      width: 720,
      height: 900,
      alt: 'Youth Red River Gorge Hiker T-shirt featuring the logo.'
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
    slug: 'kids-tshirt',
    title: 'Kids T-Shirt',
    description: 'Kids Red River Gorge Hiker T-shirt presented with the logo on the chest.',
    priceLabel: 'From $19',
    specification: 'Kids T-Shirt · Chest presentation',
    optionNote: '$19 across the verified sizes. RedRiverGorgeHiker.com promotes the Chest presentation only.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=kids-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-kids-tshirt-1e1f102d.avif`,
      width: 720,
      height: 900,
      alt: 'Kids Red River Gorge Hiker T-shirt with the logo on the chest.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'greeting-cards',
    title: 'Greeting Cards',
    description: 'A pack of 10 Red River Gorge Hiker logo greeting cards with an optional buyer-entered inside message.',
    priceLabel: '$30',
    specification: 'Pack of 10',
    optionNote: 'Buyer may enter an optional inside message on Fine Art America.',
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
    slug: 'baby-one-piece',
    title: 'Baby One-Piece',
    description: 'Red River Gorge Hiker baby one-piece featuring the logo.',
    priceLabel: 'From $23',
    specification: 'Baby One-Piece',
    optionNote: '$23 across the verified sizes.',
    fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=one-piece',
    image: {
      avif: `${assetBase}rrgh-merch-baby-one-piece-69853ef4.avif`,
      width: 720,
      height: 900,
      alt: 'Red River Gorge Hiker baby one-piece featuring the logo.'
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
