/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === 'development';
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const nextConfig = {
  // Production: static export for nginx
  // Development: use dev server with hot reload
  ...(isDev ? {} : { output: 'export' }),

  // Disable image optimization for static export
  images: {
    unoptimized: true,
  },

  reactStrictMode: true,
  swcMinify: true,

  // Trailing slash ensures consistent routing
  trailingSlash: true,

  // Development mode: proxy API requests to backend
  ...(isDev && {
    async rewrites() {
      return [
        {
          source: '/api/:path*',
          destination: `${API_URL}/api/:path*`,
        },
        {
          source: '/health',
          destination: `${API_URL}/health`,
        },
        {
          source: '/status',
          destination: `${API_URL}/status`,
        },
      ];
    },
  }),
};

module.exports = nextConfig;
