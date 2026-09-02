import { merchandiseProducts, type MerchandiseProduct } from './merchandise';

export type GearProduct = Omit<MerchandiseProduct, 'lastVerified'> & {
  lastVerified: string;
  detailPricing?: readonly string[];
  detailCustomizationNote?: string;
  detailFulfillmentNote?: string;
};

export type StorefrontGearProduct = GearProduct & {
  storefrontSubtitle: string;
  storefrontNote?: string;
};

const assetBase = 'assets/merchandise/' as const;

export const doubleRainbowGreetingCard: GearProduct = {
  slug: 'double-rainbow-eagles-point-buttress-greeting-card',
  title: 'Double Rainbow at Eagle’s Point Buttress Greeting Card',
  description: 'A greeting-card-only presentation of Double Rainbow at Eagle’s Point Buttress, offered through the Red River Gorge Hiker Store.',
  priceLabel: 'From $6.25',
  specification: 'Greeting card only',
  storeUrl: 'https://store.redrivergorgehiker.com/featured/double-rainbow-at-eagles-point-ryan-d-lewis.html?product=greeting-card',
  image: {
    avif: 'assets/merchandise/rrgh-merch-double-rainbow-greeting-card-3d945e8a.avif',
    width: 1000,
    height: 750,
    alt: 'Folded greeting card featuring Double Rainbow at Eagle’s Point Buttress displayed on a wooden table.'
  },
  detailPricing: [
    'Single Card — $6.25',
    'Pack of 10 — $35.00 total ($3.50 per card)',
    'Pack of 25 — $53.00 total (Store displays $2.12 per card)'
  ],
  detailCustomizationNote: 'The Red River Gorge Hiker Store allows the buyer to enter an optional inside message.',
  detailFulfillmentNote: 'The Red River Gorge Hiker Store, powered by Pixels, handles quantity selection, optional inside-message customization, checkout, payment, production, fulfillment, and shipping.',
  lastVerified: '2026-08-22'
};

export const longSleeveTshirt: GearProduct = {
  slug: 'long-sleeve-tshirt',
  title: 'Long-Sleeve T-Shirt',
  description: 'A charcoal Red River Gorge Hiker long-sleeve T-shirt featuring the logo centered on the chest.',
  priceLabel: 'From $29',
  specification: 'Long Sleeve T-Shirt · Medium shown · Charcoal',
  optionNote: 'Medium verified at $29 customer retail · The Red River Gorge Hiker Store lists higher pricing for 2XL, so retail pricing is size-dependent.',
  storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=long-sleeve-tshirt',
  image: {
    avif: `${assetBase}rrgh-merch-tshirt-long-sleeve-08342fea.avif`,
    width: 800,
    height: 1000,
    alt: 'Woman wearing a charcoal Red River Gorge Hiker long-sleeve T-shirt with the logo centered on the chest.'
  },
  lastVerified: '2026-08-28'
};

export const mensTankTop: GearProduct = {
  slug: 'mens-tank-top',
  title: 'Men’s Tank Top',
  description: 'A charcoal Red River Gorge Hiker men’s tank top featuring the logo centered on the chest.',
  priceLabel: 'From $25',
  specification: 'Men’s Tank Top · Medium shown · Charcoal',
  optionNote: 'Medium verified at $25 customer retail · The Red River Gorge Hiker Store lists higher pricing for 2XL, so retail pricing is size-dependent.',
  storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tank-top-tshirt',
  image: {
    avif: `${assetBase}rrgh-merch-tshirt-mens-tank-3fe72b20.avif`,
    width: 800,
    height: 1000,
    alt: 'Man wearing a dark Red River Gorge Hiker tank top with the logo centered on the chest at a gorge overlook.'
  },
  lastVerified: '2026-08-28'
};

export const toddlerTshirt: GearProduct = {
  slug: 'toddler-tshirt',
  title: 'Toddler T-Shirt',
  description: 'A charcoal Red River Gorge Hiker toddler T-shirt featuring the logo centered on the chest.',
  priceLabel: '$19',
  specification: 'Toddler T-Shirt · Medium (3T) shown · Charcoal',
  optionNote: 'Medium (3T) verified at $19 customer retail.',
  storeUrl: 'https://store.redrivergorgehiker.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=toddler-tshirt',
  image: {
    avif: `${assetBase}rrgh-merch-tshirt-toddler-f7d76ed9.avif`,
    width: 1000,
    height: 941,
    alt: 'Smiling toddler wearing a charcoal Red River Gorge Hiker logo T-shirt on a wooded trail.'
  },
  lastVerified: '2026-08-28'
};

const storefrontCopy = {
  'double-rainbow-eagles-point-buttress-greeting-card': {
    subtitle: 'Send a little piece of the Gorge',
    note: 'Double Rainbow photograph · Optional inside message'
  },
  'tshirt-chest-logo': {
    subtitle: 'Classic RRGH athletic-fit tee',
    note: 'Chest logo · Multiple sizes available'
  },
  'sticker': {
    subtitle: 'Take the Gorge with you',
    note: '3 × 3 in. RRGH logo sticker'
  },
  'tote-bag': {
    subtitle: 'Carry the Gorge wherever you go',
    note: '18 × 18 in. logo tote'
  },
  'tshirt-regular-fit': {
    subtitle: 'Everyday RRGH regular-fit tee',
    note: 'Chest logo · Multiple sizes available'
  },
  'womens-tshirt': {
    subtitle: 'Everyday RRGH women’s tee',
    note: 'Chest logo · Multiple sizes available'
  },
  'long-sleeve-tshirt': {
    subtitle: 'Classic RRGH long-sleeve tee',
    note: 'Chest logo · Charcoal shown'
  },
  'sweatshirt': {
    subtitle: 'RRGH warmth for cooler days',
    note: 'Pullover style · Chest logo'
  },
  'tshirt-pocket-logo': {
    subtitle: 'A subtler take on the RRGH tee',
    note: 'Athletic fit · Pocket logo'
  },
  'throw-pillow': {
    subtitle: 'Bring a little Gorge style home',
    note: '14 × 14 in. · Insert optional'
  },
  'mens-tank-top': {
    subtitle: 'RRGH tank for warm-weather days',
    note: 'Chest logo · Charcoal shown'
  },
  'womens-tank-top': {
    subtitle: 'RRGH tank for sunny trail days',
    note: 'Chest logo · Multiple sizes available'
  },
  'fleece-sherpa-blanket': {
    subtitle: 'Wrap up in Red River Gorge Hiker',
    note: '50 × 60 in. · Plush or Sherpa fleece'
  },
  'youth-tshirt': {
    subtitle: 'RRGH style for young explorers',
    note: 'Chest logo · Multiple sizes available'
  },
  'spiral-notebook': {
    subtitle: 'A place for trail notes and ideas',
    note: '6 × 8 in. spiral notebook'
  },
  'kids-tshirt': {
    subtitle: 'RRGH style for little explorers',
    note: 'Chest logo · Multiple sizes available'
  },
  'toddler-tshirt': {
    subtitle: 'RRGH tee for the littlest explorers',
    note: 'Chest logo · Charcoal shown'
  },
  'greeting-cards': {
    subtitle: 'Share Red River Gorge Hiker with someone',
    note: 'RRGH logo cards · Optional inside message'
  },
  'baby-one-piece': {
    subtitle: 'Start them young with RRGH',
    note: 'Logo one-piece · Multiple sizes available'
  }
} as const;

const orderedGearProducts: readonly GearProduct[] = [
  doubleRainbowGreetingCard,
  ...merchandiseProducts.slice(0, 5),
  longSleeveTshirt,
  ...merchandiseProducts.slice(5, 8),
  mensTankTop,
  ...merchandiseProducts.slice(8, 13),
  toddlerTshirt,
  ...merchandiseProducts.slice(13)
];

export const gearProducts: readonly StorefrontGearProduct[] = orderedGearProducts.map((product) => {
  const copy = storefrontCopy[product.slug as keyof typeof storefrontCopy];

  if (!copy) {
    throw new Error(`Missing storefront copy for Gear product: ${product.slug}`);
  }

  return {
    ...product,
    storefrontSubtitle: copy.subtitle,
    ...('note' in copy ? { storefrontNote: copy.note } : {})
  };
});