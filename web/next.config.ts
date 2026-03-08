import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  async rewrites() {
    return [
      {
        source: "/health",
        destination: "http://localhost:8000/health",
      },
      {
        source: "/metrics",
        destination: "http://localhost:8000/metrics",
      },
      {
        source: "/v1/:path*",
        destination: "http://localhost:8000/v1/:path*",
      },
    ];
  },
};

export default nextConfig;
