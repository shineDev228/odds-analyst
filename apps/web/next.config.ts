import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";
const PRODUCTION = process.env.NODE_ENV === "production";

/**
 * En-têtes appliqués à toutes les pages.
 *
 * La CSP est posée par `src/middleware.ts` car elle dépend d'un nonce en
 * production. HSTS n'est envoyé qu'en production : en développement,
 * l'interface est servie en HTTP simple.
 */
const enTetesSecurite = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-DNS-Prefetch-Control", value: "off" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    value:
      "accelerometer=(), camera=(), geolocation=(), microphone=(), payment=(), usb=()",
  },
  ...(PRODUCTION
    ? [
        {
          key: "Strict-Transport-Security",
          value: "max-age=63072000; includeSubDomains",
        },
      ]
    : []),
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // L'interface et l'API restent en même origine : cookies et CSRF sans CORS.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: enTetesSecurite }];
  },
};

export default nextConfig;
