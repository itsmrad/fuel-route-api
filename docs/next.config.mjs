import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // Docker copies only .next/standalone (+ static, public) into the runtime image.
  output: 'standalone',
  // Django's URLs end in "/"; without this Next 308s /api/route/ -> /api/route before app/api proxies it.
  skipTrailingSlashRedirect: true,
  async redirects() {
    return [{ source: '/', destination: '/docs', permanent: false }];
  },
};

export default withMDX(config);
