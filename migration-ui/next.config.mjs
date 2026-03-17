/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Proxy all /api/* requests to the FastAPI backend during development
  async rewrites() {
    return [
      {
        source:      "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },

  // Allow Monaco editor web workers
  webpack(config) {
    config.resolve.fallback = { fs: false, path: false };
    return config;
  },
};

export default nextConfig;
