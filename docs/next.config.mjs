import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

// Django serves the API. The browser only ever talks to this origin, so no CORS.
// Read when the config loads (dev start / build). In production Caddy routes /api/* before Next sees it.
const apiOrigin = process.env.API_ORIGIN ?? 'http://127.0.0.1:8000';

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // Django's URLs end in "/"; without this Next 308s /api/route/ -> /api/route.
  skipTrailingSlashRedirect: true,
  async redirects() {
    return [{ source: '/', destination: '/docs', permanent: false }];
  },
  async rewrites() {
    return [
      { source: '/api/:path*/', destination: `${apiOrigin}/api/:path*/` },
      { source: '/api/:path*', destination: `${apiOrigin}/api/:path*` },
    ];
  },
};

export default withMDX(config);
