export const MERCHANDISE_VERIFICATION_DATE = '2026-08-10' as const;

export interface MerchandiseProduct {
  slug: string;
  title: string;
  description: string;
  priceLabel: string;
  specification: string;
  optionNote?: string;
  storeUrl: string;
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
    description: 'Athletic-fit Red River Gorge Hiker T-shirt with the logo centered on the chest.',
    priceLabel: 'From $25',
    specification: 'Men’s T-Shirt · Athletic Fit',
    optionNote: 'Chest Logo configuration · Sizes below 2XL verified at $25 · 2XL verified at $28.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt&completeProductSku=artworkid[70456163]-productid[clothing-23]-imagewidth[286]-imageheight[286]-targetx[72]-targety[0]-modelwidth[430]-modelheight[575]-backgroundcolor[5]-orientation[0]-size[3]',
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
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=sticker',
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
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tote-bag',
    image: {
      avif: `${assetBase}rrgh-merch-tote-bag-bc2e6737.avif`,
      width: 800,
      height: 1000,
      alt: 'Person carrying a green Red River Gorge Hiker logo tote bag outdoors.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'tshirt-regular-fit',
    title: 'Men’s T-Shirt (Regular Fit)',
    description: 'Regular-fit Red River Gorge Hiker T-shirt with the logo centered on the chest.',
    priceLabel: 'From $23',
    specification: 'Men’s T-Shirt · Regular Fit',
    optionNote: 'Through XL $23 · 2XL $26 · 3XL $28.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=regular-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-regular-ece83fde.avif`,
      width: 800,
      height: 1000,
      alt: 'Man wearing a green regular-fit Red River Gorge Hiker logo T-shirt outdoors in the Red River Gorge.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'womens-tshirt',
    title: 'Women’s T-Shirt',
    description: 'Women’s Red River Gorge Hiker T-shirt with the logo presented on the chest.',
    priceLabel: 'From $25',
    specification: 'Women’s T-Shirt · Chest Logo',
    optionNote: 'Through XL $25 · 2XL $28.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=womens-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-womens-d77d1bbf.avif`,
      width: 800,
      height: 1000,
      alt: 'Woman wearing a navy Red River Gorge Hiker logo T-shirt with the logo centered on the chest.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'sweatshirt',
    title: 'Sweatshirt',
    description: 'Red River Gorge Hiker pullover sweatshirt with the logo presented on the chest.',
    priceLabel: 'From $45',
    specification: 'Pullover sweatshirt · Chest Logo',
    optionNote: 'Below 2XL $45 · 2XL $51 · 3XL $57.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=pull-over-hoodie-sweatshirt',
    image: {
      avif: `${assetBase}rrgh-merch-sweater-df6f24ea.avif`,
      width: 800,
      height: 1000,
      alt: 'Man wearing a dark Red River Gorge Hiker logo pullover sweatshirt outdoors in autumn.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'tshirt-pocket-logo',
    title: 'Men’s T-Shirt (Athletic Fit) — Pocket Logo',
    description: 'Athletic-fit Red River Gorge Hiker T-shirt with a small logo at the pocket position.',
    priceLabel: 'From $25',
    specification: 'Men’s T-Shirt · Athletic Fit',
    optionNote: 'Pocket Logo configuration · Sizes below 2XL verified at $25 · 2XL verified at $28.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=adult-tshirt&completeProductSku=artworkid[70456163]-productid[clothing-23]-imagewidth[430]-imageheight[430]-targetx[0]-targety[0]-modelwidth[430]-modelheight[575]-backgroundcolor[5]-orientation[0]-size[3]-designlocation[pocket]',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-pocket-v3-e3c01e3d.avif`,
      width: 800,
      height: 1000,
      alt: 'Man wearing a navy athletic-fit T-shirt with a small Red River Gorge Hiker logo at the pocket position.'
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
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=throw-pillow',
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
    description: 'Women’s Red River Gorge Hiker tank top with the logo presented on the chest.',
    priceLabel: 'From $25',
    specification: 'Women’s Tank Top · Chest Logo',
    optionNote: 'Verified at $25 across sizes.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=womens-tank-top',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-womens-tank-9998df0a.avif`,
      width: 750,
      height: 1000,
      alt: 'Woman wearing a white Red River Gorge Hiker logo tank top outdoors in the Red River Gorge.'
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
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=fleece-blanket',
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
    description: 'Youth Red River Gorge Hiker T-shirt featuring the logo on the chest.',
    priceLabel: 'From $21',
    specification: 'Youth T-Shirt',
    optionNote: 'Verified at $21 across sizes.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=youth-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-youth-f9cdcdd6.avif`,
      width: 800,
      height: 1000,
      alt: 'Boy wearing a green Red River Gorge Hiker logo youth T-shirt on a wooded trail.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'spiral-notebook',
    title: 'Spiral Notebook',
    description: 'A 6 × 8-inch green spiral notebook featuring the Red River Gorge Hiker logo.',
    priceLabel: '$16',
    specification: '6 × 8 inches',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=spiral-notebook',
    image: {
      avif: `${assetBase}rrgh-merch-spiral-notebook-62906115.avif`,
      width: 800,
      height: 1000,
      alt: 'Green spiral notebook with the Red River Gorge Hiker logo being held and written in.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  },
  {
    slug: 'kids-tshirt',
    title: 'Kids T-Shirt',
    description: 'Kids Red River Gorge Hiker T-shirt with the logo presented on the chest.',
    priceLabel: 'From $19',
    specification: 'Kids T-Shirt · Chest Logo',
    optionNote: 'Verified at $19 across sizes.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=kids-tshirt',
    image: {
      avif: `${assetBase}rrgh-merch-tshirt-kids-813c4eae.avif`,
      width: 800,
      height: 1000,
      alt: 'Girl wearing a dark Red River Gorge Hiker logo kids T-shirt outdoors at a gorge overlook.'
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
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=greeting-card',
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
    description: 'Baby one-piece featuring the Red River Gorge Hiker logo on the chest.',
    priceLabel: 'From $23',
    specification: 'Baby One-Piece',
    optionNote: 'Verified at $23 across sizes.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=one-piece',
    image: {
      avif: `${assetBase}rrgh-merch-one-piece-37bc434d.avif`,
      width: 800,
      height: 1000,
      alt: 'Baby wearing a dark Red River Gorge Hiker logo one-piece while being held by an adult.'
    },
    lastVerified: MERCHANDISE_VERIFICATION_DATE
  }
] as const;