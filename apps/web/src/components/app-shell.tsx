"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { apiFetch, messageErreur } from "@/lib/api";
import type { EtatAuth } from "@/lib/types";
import { fr } from "@/messages/fr";

import { Chargement } from "./ui";

interface ItemNavigation {
  href: string;
  libelle: string;
  symbole: string;
}

const groupesNavigation: Array<{ titre: string; items: ItemNavigation[] }> = [
  {
    titre: "Référentiel",
    items: [
      { href: "/tableau-de-bord", libelle: "Tableau de bord", symbole: "◧" },
      { href: "/competitions", libelle: "Compétitions", symbole: "▤" },
      { href: "/equipes", libelle: "Équipes", symbole: "◉" },
      { href: "/rencontres", libelle: "Rencontres", symbole: "◈" },
    ],
  },
  {
    titre: "Analyse",
    items: [
      { href: "/combinaisons", libelle: "Combinaisons", symbole: "∑" },
      { href: "/historique", libelle: "Historique", symbole: "◷" },
      { href: "/calibration", libelle: "Calibration", symbole: "◎" },
    ],
  },
  {
    titre: "Système",
    items: [
      { href: "/synchronisation", libelle: "Synchronisation", symbole: "⇄" },
      { href: "/parametres", libelle: "Paramètres", symbole: "⚙" },
    ],
  },
];

const navigation = groupesNavigation.flatMap((groupe) => groupe.items);

function estActif(chemin: string, href: string): boolean {
  return chemin === href || chemin.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const chemin = usePathname();
  const [etat, setEtat] = useState<EtatAuth | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const charger = useCallback(async () => {
    try {
      const statut = await apiFetch<EtatAuth>("/v1/auth/status", { anonyme: true });
      if (!statut.admin_configured) {
        router.replace("/premiere-utilisation");
        return;
      }
      if (!statut.authenticated) {
        router.replace("/connexion");
        return;
      }
      setEtat(statut);
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }, [router]);

  useEffect(() => {
    void charger();
  }, [charger]);

  async function seDeconnecter() {
    try {
      await apiFetch<void>("/v1/auth/logout", { methode: "POST" });
    } catch {
      // La session est peut-être déjà expirée : on redirige quand même.
    }
    router.replace("/connexion");
  }

  if (erreur) {
    return (
      <div className="mx-auto max-w-xl px-5 py-16">
        <div className="border-l-2 border-danger/60 pl-3 text-sm text-danger">{erreur}</div>
      </div>
    );
  }

  if (!etat) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Chargement libelle="Vérification de la session…" />
      </div>
    );
  }

  const sectionActive = navigation.find((item) => estActif(chemin, item.href))?.libelle;

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-bordure bg-fond-panneau lg:w-64 lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-3 px-5 py-5">
          <div
            aria-hidden
            className="flex size-9 items-center justify-center rounded-md border border-accent/50 text-sm font-semibold text-accent"
          >
            OA
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight">{fr.app.nom}</p>
            <p className="text-xs text-texte-faible">{fr.app.sousTitre}</p>
          </div>
        </div>

        <nav aria-label="Navigation principale" className="min-w-0 px-3 pb-3 lg:flex-1">
          <ul className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:hidden">
            {navigation.map((item) => {
              const actif = estActif(chemin, item.href);
              return (
                <li key={item.href} className="w-full">
                  <Link
                    href={item.href}
                    aria-current={actif ? "page" : undefined}
                    className={`flex h-9 items-center gap-2 rounded-md border-l-2 px-2.5 text-xs font-medium transition ${
                      actif
                        ? "border-accent bg-accent/10 text-accent"
                        : "border-transparent text-texte-doux hover:bg-fond-eleve hover:text-texte"
                    }`}
                  >
                    <span aria-hidden className="w-4 text-center">
                      {item.symbole}
                    </span>
                    {item.libelle}
                  </Link>
                </li>
              );
            })}
          </ul>

          <div className="hidden lg:block">
            {groupesNavigation.map((groupe) => (
              <div key={groupe.titre} className="mb-4 last:mb-0">
                <p className="px-3 pb-1 text-xs text-texte-faible">{groupe.titre}</p>
                <ul className="flex flex-col gap-0.5">
                  {groupe.items.map((item) => {
                    const actif = estActif(chemin, item.href);
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          aria-current={actif ? "page" : undefined}
                          className={`flex h-9 items-center gap-2.5 rounded-md border-l-2 px-3 text-sm transition ${
                            actif
                              ? "border-accent bg-accent/10 font-medium text-accent"
                              : "border-transparent text-texte-doux hover:bg-fond-eleve hover:text-texte"
                          }`}
                        >
                          <span aria-hidden className="w-4 text-center text-sm">
                            {item.symbole}
                          </span>
                          {item.libelle}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </nav>

        <div className="hidden border-t border-bordure px-5 py-4 lg:block">
          <p className="truncate text-xs text-texte-faible" title={etat.user?.email}>
            {etat.user?.email}
          </p>
          <button
            type="button"
            onClick={() => void seDeconnecter()}
            className="mt-2 text-xs font-medium text-texte-doux transition hover:text-danger"
          >
            Se déconnecter
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-bordure px-5 py-2">
          <p className="text-xs text-texte-faible">{sectionActive ?? "Espace de travail"}</p>
          <button
            type="button"
            onClick={() => void seDeconnecter()}
            className="shrink-0 text-xs font-medium text-texte-doux transition hover:text-danger lg:hidden"
          >
            Quitter
          </button>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-6 sm:px-8">{children}</main>

        <footer className="border-t border-bordure px-5 py-4 text-xs text-texte-faible sm:px-8">
          Usage strictement personnel. Aucune donnée de bookmaker n&apos;est stockée. Aucun pari
          n&apos;est placé automatiquement.
        </footer>
      </div>
    </div>
  );
}
