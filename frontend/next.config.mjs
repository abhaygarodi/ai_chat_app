const rawBackend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const backend = rawBackend.endsWith("/") ? rawBackend.slice(0, -1) : rawBackend;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/:path*`,
      },
    ];
  },
};

export default nextConfig;

