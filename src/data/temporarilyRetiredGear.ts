export const CHILDREN_APPAREL_FULFILLMENT_HOLD =
  'TEMPORARILY RETIRED FROM RRGH WEBSITE — FAA/PIXELS CHILDREN’S-APPAREL FULFILLMENT HOLD — 2026-09-22' as const;

export const temporarilyRetiredChildrenApparel = [
  {
    slug: 'youth-tshirt',
    title: 'Youth T-Shirt',
    description: 'Youth Red River Gorge Hiker T-shirt featuring the logo on the chest.',
    priceLabel: 'From $21',
    specification: 'Youth T-Shirt',
    optionNote: 'Verified at $21 across sizes.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=youth-tshirt',
    image: {
      avif: 'assets/merchandise/rrgh-merch-tshirt-youth-f9cdcdd6.avif',
      width: 800,
      height: 1000,
      alt: 'Boy wearing a green Red River Gorge Hiker logo youth T-shirt on a wooded trail.'
    },
    lastVerified: '2026-08-10',
    websiteState: CHILDREN_APPAREL_FULFILLMENT_HOLD
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
      avif: 'assets/merchandise/rrgh-merch-tshirt-kids-813c4eae.avif',
      width: 800,
      height: 1000,
      alt: 'Girl wearing a dark Red River Gorge Hiker logo kids T-shirt outdoors at a gorge overlook.'
    },
    lastVerified: '2026-08-10',
    websiteState: CHILDREN_APPAREL_FULFILLMENT_HOLD
  },
  {
    slug: 'toddler-tshirt',
    title: 'Toddler T-Shirt',
    description: 'A charcoal Red River Gorge Hiker toddler T-shirt featuring the logo centered on the chest.',
    priceLabel: '$19',
    specification: 'Toddler T-Shirt · Medium (3T) shown · Charcoal',
    optionNote: 'Medium (3T) verified at $19 customer retail.',
    storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=toddler-tshirt',
    image: {
      avif: 'assets/merchandise/rrgh-merch-tshirt-toddler-f7d76ed9.avif',
      width: 1000,
      height: 941,
      alt: 'Smiling toddler wearing a charcoal Red River Gorge Hiker logo T-shirt on a wooded trail.'
    },
    lastVerified: '2026-08-28',
    websiteState: CHILDREN_APPAREL_FULFILLMENT_HOLD
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
      avif: 'assets/merchandise/rrgh-merch-one-piece-37bc434d.avif',
      width: 800,
      height: 1000,
      alt: 'Baby wearing a dark Red River Gorge Hiker logo one-piece while being held by an adult.'
    },
    lastVerified: '2026-08-10',
    websiteState: CHILDREN_APPAREL_FULFILLMENT_HOLD
  }
] as const;
