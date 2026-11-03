import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: { proxyTimeout: 600_000 },
  distDir: process.env.NODE_ENV === "production" ? ".next-build" : ".next-dev",
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${process.env.SENTINEL_API_URL ?? "http://127.0.0.1:8000"}/:path*` }];
  },
};

export default nextConfig;
