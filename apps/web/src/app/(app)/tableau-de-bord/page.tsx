"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  Alerte,
  Badge,
  Chargement,
  EtatVide,
  Panneau,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import type { ResumeTableauDeBord } from "@/lib/types";

function CarteIndicateur({ libelle, valeur }: { libelle: string; valeur: number }) {
  return (
    <div className="rounded-2xl border border-bordure bg-fond-panneau p-4">
      <p className="text-[11px] uppercase tracking-wide text-texte-faible">{libelle}</p>
      <p className="mt-1 font-mono text-2xl font-semibold text-texte">{valeur}</p>
    </div>
  );
}

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
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Tableau de bord</h1>
        <p className="mt-1 text-xs text-texte-doux">
          Vue d&apos;ensemble de votre référentiel et des prochaines rencontres.
        </p>
      </header>

      <Alerte ton="avertissement">{resume.avertissement}</Alerte>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <CarteIndicateur libelle="Compétitions" valeur={resume.competitions} />
        <CarteIndicateur libelle="Équipes" valeur={resume.teams} />
        <CarteIndicateur libelle="Rencontres" valeur={resume.matches} />
        <CarteIndicateur libelle="À venir (14 j)" valeur={resume.matchs_a_venir} />
        <CarteIndicateur libelle="Terminées" valeur={resume.matchs_termines} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panneau
          titre="Prochaines rencontres"
          description="Les cinq rencontres programmées les plus proches."
          action={
            <Link href="/rencontres" className="text-[11px] font-medium text-accent hover:underline">
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
            <ul className="flex flex-col divide-y divide-bordure">
              {resume.prochaines_rencontres.map((rencontre) => (
                <li key={rencontre.id}>
                  <Link
                    href={`/rencontres/${rencontre.id}`}
                    className="flex items-center justify-between gap-3 py-2.5 transition hover:text-accent"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm text-texte">
                        {rencontre.home_team_name} — {rencontre.away_team_name}
                      </p>
                      <p className="truncate text-[11px] text-texte-faible">
                        {rencontre.competition_name} · {rencontre.season_label}
                      </p>
                    </div>
                    <span className="shrink-0 text-right text-[11px] text-texte-doux">
                      {formatDateHeure(rencontre.kickoff_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panneau>

        <Panneau titre="Derniers résultats" description="Les cinq dernières rencontres terminées.">
          {resume.derniers_resultats.length === 0 ? (
            <EtatVide>Aucun résultat enregistré pour le moment.</EtatVide>
          ) : (
            <ul className="flex flex-col divide-y divide-bordure">
              {resume.derniers_resultats.map((rencontre) => (
                <li key={rencontre.id}>
                  <Link
                    href={`/rencontres/${rencontre.id}`}
                    className="flex items-center justify-between gap-3 py-2.5 transition hover:text-accent"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm text-texte">
                        {rencontre.home_team_name} — {rencontre.away_team_name}
                      </p>
                      <p className="truncate text-[11px] text-texte-faible">
                        {formatDateHeure(rencontre.kickoff_at)}
                      </p>
                    </div>
                    <Badge ton="succes">
                      {rencontre.home_score ?? "—"} : {rencontre.away_score ?? "—"}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panneau>
      </div>
    </div>
  );
}
