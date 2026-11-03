import type { Metadata } from "next";

import { fr } from "@/messages/fr";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: `${fr.app.nom} — ${fr.app.sousTitre}`,
    template: `%s — ${fr.app.nom}`,
  },
  description:
    "Application personnelle d'analyse statistique sportive : estimation de probabilités, comparaison aux cotes et construction de combinaisons.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
