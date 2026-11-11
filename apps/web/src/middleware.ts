/**
 * En-têtes de sécurité de l'interface.
 *
 * La politique de sécurité du contenu (CSP) est posée ici, et non dans
 * `next.config.ts`, car elle doit changer entre développement et production :
 *
 * - en développement, React et le rafraîchissement à chaud ont besoin de
 *   `unsafe-inline` et `unsafe-eval` ;
 * - en production, chaque script Next.js reçoit un nonce aléatoire, ce qui
 *   bloque l'injection de scripts tiers tout en laissant l'application
 *   fonctionner (`strict-dynamic`).
 *
 * Les requêtes `/api` sont exclues : l'API FastAPI pose ses propres en-têtes.
 */

import { NextResponse, type NextRequest } from "next/server";

const PRODUCTION = process.env.NODE_ENV === "production";

const DIRECTIVES_COMMUNES = [
  "default-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
];

function construireCsp(nonce: string | null): string {
  const script = PRODUCTION
    ? `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`
    : "script-src 'self' 'unsafe-inline' 'unsafe-eval'";

  // `connect-src` doit autoriser le websocket du rafraîchissement à chaud.
  const connect = PRODUCTION ? "connect-src 'self'" : "connect-src 'self' ws: wss:";

  const directives = [...DIRECTIVES_COMMUNES, script, connect];
  if (PRODUCTION) {
    directives.push("upgrade-insecure-requests");
  }
  return directives.join("; ");
}

export function middleware(request: NextRequest) {
  // En développement, aucun nonce n'est nécessaire : React insère des scripts
  // en ligne que le navigateur doit pouvoir exécuter.
  const nonce = PRODUCTION ? Buffer.from(crypto.randomUUID()).toString("base64") : null;
  const csp = construireCsp(nonce);

  const entetesRequete = new Headers(request.headers);
  entetesRequete.set("Content-Security-Policy", csp);
  if (nonce) {
    entetesRequete.set("x-nonce", nonce);
  }

  const reponse = NextResponse.next({ request: { headers: entetesRequete } });
  reponse.headers.set("Content-Security-Policy", csp);
  return reponse;
}

export const config = {
  matcher: [
    {
      // Tout sauf l'API, les ressources Next.js et les fichiers de métadonnées.
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
