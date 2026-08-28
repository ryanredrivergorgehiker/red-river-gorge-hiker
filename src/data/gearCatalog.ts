import { merchandiseProducts, type MerchandiseProduct } from './merchandise';

export type GearProduct = Omit<MerchandiseProduct, 'lastVerified'> & {
  lastVerified: string;
  detailPricing?: readonly string[];
  detailCustomizationNote?: string;
  detailFulfillmentNote?: string;
};

const assetBase = 'assets/merchandise/' as const;

export const doubleRainbowGreetingCard: GearProduct = {
  slug: 'double-rainbow-eagles-point-buttress-greeting-card',
  title: 'Double Rainbow at Eagle’s Point Buttress Greeting Card',
  description: 'A greeting-card-only presentation of Double Rainbow at Eagle’s Point Buttress, offered through Fine Art America.',
  priceLabel: 'From $6.25',
  specification: 'Greeting card only',
  fineArtAmericaUrl: 'https://fineartamerica.com/featured/double-rainbow-at-eagles-point-ryan-d-lewis.html?product=greeting-card',
  image: {
    avif: 'assets/merchandise/rrgh-merch-double-rainbow-greeting-card-3d945e8a.avif',
    width: 1000,
    height: 750,
    alt: 'Folded greeting card featuring Double Rainbow at Eagle’s Point Buttress displayed on a wooden table.'
  },
  detailPricing: [
    'Single Card — $6.25',
    'Pack of 10 — $35.00 total ($3.50 per card)',
    'Pack of 25 — $53.00 total (FAA displays $2.12 per card)'
  ],
  detailCustomizationNote: 'Fine Art America allows the buyer to enter an optional inside message.',
  detailFulfillmentNote: 'Fine Art America handles quantity selection, optional inside-message customization, checkout, payment, production, fulfillment, and shipping.',
  lastVerified: '2026-08-22'
};

export const longSleeveTshirt: GearProduct = {
  slug: 'long-sleeve-tshirt',
  title: 'Long-Sleeve T-Shirt',
  description: 'A charcoal Red River Gorge Hiker long-sleeve T-shirt featuring the logo centered on the chest.',
  priceLabel: 'From $29',
  specification: 'Long Sleeve T-Shirt · Medium shown · Charcoal',
  optionNote: 'Medium verified at $29 customer retail · Fine Art America lists higher base pricing for 2XL, so retail pricing is size-dependent.',
  fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=long-sleeve-tshirt',
  image: {
    avif: `${assetBase}rrgh-merch-tshirt-long-sleeve-b245685d.avif`,
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
  optionNote: 'Medium verified at $25 customer retail · Fine Art America lists higher base pricing for 2XL, so retail pricing is size-dependent.',
  fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=tank-top-tshirt',
  image: {
    avif: `${assetBase}rrgh-merch-tshirt-mens-tank-90f189fc.avif`,
    width: 800,
    height: 1000,
    alt: 'Man wearing a dark Red River Gorge Hiker tank top with the logo centered on the chest at a gorge overlook.'
  },
  lastVerified: '2026-08-28'
};

export const handTowel: GearProduct = {
  slug: 'hand-towel',
  title: 'Hand Towel',
  description: 'A green Red River Gorge Hiker hand towel featuring the logo in a vertical presentation.',
  priceLabel: '$14.50',
  specification: 'Hand Towel · 15 × 30 inches · Vertical',
  optionNote: 'Hand Towel configuration verified at $14.50 customer retail · Background R(34) G(85) B(58).',
  fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=bath-towel',
  image: {
    avif: `${assetBase}rrgh-merch-towel-hand-f1f88236.avif`,
    width: 800,
    height: 1000,
    alt: 'Green Red River Gorge Hiker logo hand towel displayed in a bathroom setting.'
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
  fineArtAmericaUrl: 'https://fineartamerica.com/featured/red-river-gorge-hiker-ryan-d-lewis.html?product=toddler-tshirt',
  image: {
    avif: `${assetBase}rrgh-merch-tshirt-toddler-7e00729e.avif`,
    width: 1000,
    height: 941,
    alt: 'Smiling toddler wearing a charcoal Red River Gorge Hiker logo T-shirt on a wooded trail.'
  },
  lastVerified: '2026-08-28'
};

export const gearProducts: readonly GearProduct[] = [
  doubleRainbowGreetingCard,
  ...merchandiseProducts.slice(0, 6),
  longSleeveTshirt,
  ...merchandiseProducts.slice(6, 9),
  mensTankTop,
  ...merchandiseProducts.slice(9, 14),
  handTowel,
  ...merchandiseProducts.slice(14, 17),
  toddlerTshirt,
  ...merchandiseProducts.slice(17)
];
