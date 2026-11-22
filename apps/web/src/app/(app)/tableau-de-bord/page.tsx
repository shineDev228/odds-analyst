"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  Alerte,
  Chargement,
  EntetePage,
  EtatVide,
  Indicateur,
  Section,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { formatDateCourte, formatHeure } from "@/lib/format";
import type { ResumeTableauDeBord } from "@/lib/types";

export default function PageTableauDeBord() {
  const [resume, setResume] = useState<ResumeTableauDeBord | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        const donnees = await apiFetch<ResumeTableauDeBord>("/v1/dashboard/summary");
        if (actif) setResume(donnees);
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      }
    })();
    return () => {
      actif = false;
    };
  }, []);

  if (erreur) return <Alerte ton="erreur">{erreur}</Alerte>;
  if (!resume) return <Chargement />;

  return (
    <div className="flex flex-col gap-6">
      <EntetePage
        titre="Tableau de bord"
        description="Vue d'ensemble du référentiel et des prochaines rencontres."
      />

      <Alerte ton="avertissement">{resume.avertissement}</Alerte>

      <Section
        titre="Référentiel"
        description="Ce que contient la base aujourd'hui."
        className="pt-4"
      >
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
          <Indicateur libelle="Compétitions" valeur={String(resume.competitions)} />
          <Indicateur libelle="Équipes" valeur={String(resume.teams)} />
          <Indicateur libelle="Rencontres" valeur={String(resume.matches)} />
          <Indicateur libelle="À venir (14 j)" valeur={String(resume.matchs_a_venir)} />
          <Indicateur libelle="Terminées" valeur={String(resume.matchs_termines)} />
        </dl>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          titre="Prochaines rencontres"
          description="Les cinq rencontres programmées les plus proches."
          action={
            <Link href="/rencontres" className="text-xs font-medium text-accent hover:underline">
              Tout voir
            </Link>
          }
        >
          {resume.prochaines_rencontres.length === 0 ? (
            <EtatVide>
              Aucune rencontre programmée.{" "}
              <Link href="/rencontres" className="text-accent hover:underline">
                Ajouter une rencontre
              </Link>
            </EtatVide>
          ) : (
            <ul className="flex flex-col">
              {resume.prochaines_rencontres.map((rencontre) => (
                <li key={rencontre.id}>
                  <Link
                    href={`/rencontres/${rencontre.id}`}
                    className="grid grid-cols-[56px_1fr] items-baseline gap-3 border-b border-bordure/70 py-2.5 last:border-0 hover:bg-fond-panneau"
                  >
                    <span className="font-mono text-xs tabular-nums text-texte-doux">
                      <span className="block">{formatDateCourte(rencontre.kickoff_at)}</span>
                      <span className="block text-sm text-texte">
                        {formatHeure(rencontre.kickoff_at)}
                      </span>
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-texte">
                        {rencontre.home_team_name} — {rencontre.away_team_name}
                      </span>
                      <span className="block truncate text-xs text-texte-faible">
                        {rencontre.competition_name} · {rencontre.season_label}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          titre="Derniers résultats"
          description="Les cinq dernières rencontres terminées."
        >
          {resume.derniers_resultats.length === 0 ? (
            <EtatVide>Aucun résultat enregistré pour le moment.</EtatVide>
          ) : (
            <ul className="flex flex-col">
              {resume.derniers_resultats.map((rencontre) => (
                <li key={rencontre.id}>
                  <Link
                    href={`/rencontres/${rencontre.id}`}
                    className="grid grid-cols-[1fr_auto] items-baseline gap-3 border-b border-bordure/70 py-2.5 last:border-0 hover:bg-fond-panneau"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-texte">
                        {rencontre.home_team_name} — {rencontre.away_team_name}
                      </span>
                      <span className="block truncate text-xs text-texte-faible">
                        {formatDateCourte(rencontre.kickoff_at)} ·{" "}
                        {formatHeure(rencontre.kickoff_at)}
                      </span>
                    </span>
                    <span className="font-mono text-sm tabular-nums text-texte">
                      {rencontre.home_score ?? "—"} : {rencontre.away_score ?? "—"}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </div>
  );
}
