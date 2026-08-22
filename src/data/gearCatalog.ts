import { merchandiseProducts, type MerchandiseProduct } from './merchandise';

export type GearProduct = Omit<MerchandiseProduct, 'lastVerified'> & {
  lastVerified: string;
  detailPricing?: readonly string[];
  detailCustomizationNote?: string;
  detailFulfillmentNote?: string;
};

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

export const gearProducts: readonly GearProduct[] = [
  doubleRainbowGreetingCard,
  ...merchandiseProducts
];
