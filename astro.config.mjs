import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

const site = process.env.SITE_URL ?? 'https://redrivergorgehiker.com';
const base = process.env.BASE_PATH ?? '/';

export default defineConfig({
  site,
  base,
  output: 'static',
  integrations: [sitemap({ filter: (page) => !page.includes('/assets/images/') })],
  build: { format: 'directory' }
});
