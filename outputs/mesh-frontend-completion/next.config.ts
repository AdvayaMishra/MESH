import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: ".next-connected",
  async headers(){return [{source:"/:path*",headers:[{key:"X-Frame-Options",value:"DENY"},{key:"Content-Security-Policy",value:"frame-ancestors 'none'"},{key:"Referrer-Policy",value:"no-referrer"},{key:"X-Content-Type-Options",value:"nosniff"}]}];},
  experimental: { workerThreads: true, cpus: 2 },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
