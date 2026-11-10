import type { NextConfig } from "next";

// Origin of the Kimiko FastAPI backend. Override with KIMIKO_API_URL when the
// API is not on localhost:8000 (e.g. a remote host or a different Docker port).
const API_ORIGIN = (process.env.KIMIKO_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/health",
        destination: `${API_ORIGIN}/health`,
      },
      {
        // NOTE: the dashboard itself is served at /metrics, so the Prometheus
        // endpoint must live under a different path. A rewrite for /metrics
        // would never run because filesystem routes win over rewrites.
        source: "/api/metrics",
        destination: `${API_ORIGIN}/metrics`,
      },
      {
        source: "/v1/:path*",
        destination: `${API_ORIGIN}/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
