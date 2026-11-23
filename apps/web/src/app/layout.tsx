import type { Metadata } from "next";
import localFont from "next/font/local";

import { NotificationsProvider } from "@/components/notifications";
import { fr } from "@/messages/fr";

import "./globals.css";

const archivo = localFont({
  src: "./fonts/Archivo-latin.woff2",
  variable: "--font-archivo",
  display: "swap",
  weight: "400 600",
});

const plexMono = localFont({
  src: [
    { path: "./fonts/IBMPlexMono-400-latin.woff2", weight: "400", style: "normal" },
    { path: "./fonts/IBMPlexMono-500-latin.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: `${fr.app.nom} — ${fr.app.sousTitre}`,
    template: `%s — ${fr.app.nom}`,
  },
  description:
    "Application personnelle d'analyse statistique sportive : estimation de probabilités, comparaison aux cotes et construction de combinaisons.",
  robots: { index: false, follow: false },
};

// La CSP de production utilise un nonce différent à chaque requête. Une page
// pré-rendue statiquement ne peut pas en recevoir : le rendu doit donc être
// dynamique. Le coût est négligeable pour une application à utilisateur unique.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${archivo.variable} ${plexMono.variable}`}>
      <body className="min-h-screen antialiased">
        <NotificationsProvider>{children}</NotificationsProvider>
      </body>
    </html>
  );
}
