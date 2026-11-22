import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono } from "next/font/google";

import { fr } from "@/messages/fr";

import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
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
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
