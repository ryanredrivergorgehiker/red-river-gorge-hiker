import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
export default defineConfig({
  site: 'https://ryanredrivergorgehiker.github.io',
  base: '/red-river-gorge-hiker/',
  output: 'static',
  integrations: [sitemap({ filter: (page) => !page.includes('/assets/images/') })],
  build: { format: 'directory' }
});
