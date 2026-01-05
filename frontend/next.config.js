/** @type {import('next').NextConfig} */
const nextConfig = {
  // Generate static files for nginx to serve
  output: 'export',

  // Disable image optimization for static export
  images: {
    unoptimized: true,
  },

  reactStrictMode: true,
  swcMinify: true,

  // Trailing slash ensures consistent routing
  trailingSlash: true,
};

module.exports = nextConfig;
