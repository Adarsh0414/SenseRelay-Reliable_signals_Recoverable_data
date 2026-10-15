import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

function productionMetadata() {
  return {
    name: 'mayacardio-production-metadata',
    transformIndexHtml(html: string) {
      const configured = process.env.PUBLIC_SITE_URL || process.env.VITE_PUBLIC_SITE_URL || '';
      if (!configured.trim()) return html;
      let siteUrl: URL;
      try {
        siteUrl = new URL(configured.trim());
      } catch {
        throw new Error('PUBLIC_SITE_URL must be an absolute HTTP(S) origin before production build.');
      }
      if (!['http:', 'https:'].includes(siteUrl.protocol)) {
        throw new Error('PUBLIC_SITE_URL must use HTTP or HTTPS.');
      }
      const origin = siteUrl.origin.replace(/&/g, '&amp;').replace(/\"/g, '&quot;');
      let output = html.replace(/(<meta property=\"og:image\" content=)\"[^\"]*\"/, `$1\"${origin}/og-mayacardio.png\"`);
      if (/<meta property=\"og:url\"/.test(output)) {
        output = output.replace(/<meta property=\"og:url\" content=\"[^\"]*\" \/>/, `<meta property=\"og:url\" content=\"${origin}/\" />`);
      } else {
        output = output.replace('</head>', `    <meta property=\"og:url\" content=\"${origin}/\" />\n  </head>`);
      }
      if (/<link rel=\"canonical\"/.test(output)) {
        output = output.replace(/<link rel=\"canonical\" href=\"[^\"]*\" \/>/, `<link rel=\"canonical\" href=\"${origin}/\" />`);
      } else {
        output = output.replace('</head>', `    <link rel=\"canonical\" href=\"${origin}/\" />\n  </head>`);
      }
      return output;
    },
  };
}

export default defineConfig({
  plugins: [react(), productionMetadata()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/docs': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/openapi.json': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    assetsInlineLimit: 4096,
  },
});
