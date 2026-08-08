import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
export default defineConfig({
  site: 'https://redrivergorgehiker.com',
  base: '/',
  output: 'static',
  integrations: [sitemap({ filter: (page) => !page.includes('/assets/images/') })],
  build: { format: 'directory' }
});
