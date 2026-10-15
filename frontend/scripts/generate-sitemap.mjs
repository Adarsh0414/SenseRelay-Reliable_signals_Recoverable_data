import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const raw = process.env.PUBLIC_SITE_URL || process.env.VITE_PUBLIC_SITE_URL || '';
let url = '';
if (raw.trim()) {
  try {
    const parsed = new URL(raw.trim());
    if (!['https:', 'http:'].includes(parsed.protocol)) throw new Error('unsupported protocol');
    url = parsed.origin;
  } catch {
    console.error('PUBLIC_SITE_URL must be a valid absolute http(s) origin.');
    process.exit(1);
  }
}
const body = url
  ? `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>${url}/</loc><changefreq>monthly</changefreq><priority>1.0</priority></url></urlset>\n`
  : `<?xml version="1.0" encoding="UTF-8"?>\n<!-- Set PUBLIC_SITE_URL before a production build to generate the public canonical sitemap. -->\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>\n`;
writeFileSync(resolve('public/sitemap.xml'), body, 'utf8');
const robots = url
  ? `User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: ${url}/sitemap.xml\n`
  : `User-agent: *\nAllow: /\nDisallow: /api/\n# Set PUBLIC_SITE_URL before production build to publish a canonical sitemap.\n`;
writeFileSync(resolve('public/robots.txt'), robots, 'utf8');
console.log(url ? `Generated sitemap for ${url}` : 'Generated development sitemap; set PUBLIC_SITE_URL for production.');
