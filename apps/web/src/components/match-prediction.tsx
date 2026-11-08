"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Alerte,
  Badge,
  Bouton,
  Chargement,
  EtatVide,
  Panneau,
} from "@/components/ui";
import { ApiError, apiFetch, messageErreur } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import type { Prediction, SelectionPrediction } from "@/lib/types";

function pourcent(valeur: number, decimales = 0): string {
  return `${(valeur * 100).toLocaleString("fr-FR", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })} %`;
}

function fourchette(selection: { low: number; high: number }): string {
  return `${pourcent(selection.low)} – ${pourcent(selection.high)}`;
}

function tonQualite(niveau: string): "succes" | "accent" | "neutre" | "alerte" {
  if (niveau === "bonne") return "succes";
  if (niveau === "correcte") return "accent";
  if (niveau === "moyenne") return "neutre";
  return "alerte";
}

function BarreProbabilite({ selection }: { selection: SelectionPrediction }) {
  const gauche = Math.max(0, Math.min(100, selection.low * 100));
  const droite = Math.max(gauche, Math.min(100, selection.high * 100));
  const centre = Math.max(0, Math.min(100, selection.probability * 100));
  return (
    <div
      className="relative mt-2 h-1.5 overflow-hidden rounded-full bg-fond"
      role="img"
      aria-label={`Probabilité ${pourcent(selection.probability)}, fourchette ${fourchette(selection)}`}
    >
      <div
        className="absolute inset-y-0 bg-accent/25"
        style={{ left: `${gauche}%`, width: `${Math.max(droite - gauche, 0.8)}%` }}
      />
      <div
        className="absolute inset-y-0 w-0.5 bg-accent"
        style={{ left: `${centre}%` }}
      />
    </div>
  );
}

function CarteSelection({
  selection,
  accent = false,
}: {
  selection: SelectionPrediction;
  accent?: boolean;
}) {
  return (
    <div className="rounded-lg border border-bordure-forte bg-fond-eleve p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-medium text-texte">{selection.label}</p>
        <p className={`font-mono text-sm ${accent ? "text-accent" : "text-texte"}`}>
          {pourcent(selection.probability, 1)}
        </p>
      </div>
      <BarreProbabilite selection={selection} />
      <p className="mt-1.5 text-[11px] text-texte-faible">
        Fourchette 80 % : {fourchette(selection)}
      </p>
    </div>
  );
}

export function PanneauPrediction({
  matchId,
  equipeDomicile,
  equipeExterieur,
}: {
  matchId: string;
  equipeDomicile: string;
  equipeExterieur: string;
}) {
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [indisponible, setIndisponible] = useState<string | null>(null);

  const charger = useCallback(async () => {
    setChargement(true);
    setErreur(null);
    setIndisponible(null);
    try {
      const data = await apiFetch<Prediction>(`/v1/matches/${matchId}/prediction`);
      setPrediction(data);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setPrediction(null);
        setIndisponible(error.message);
      } else {
        setErreur(messageErreur(error));
      }
    } finally {
      setChargement(false);
    }
  }, [matchId]);

  useEffect(() => {
    void charger();
  }, [charger]);

  return (
    <Panneau
      titre="Analyse statistique (modèle v1)"
      description="Probabilités estimées à partir des résultats passés. Chaque valeur est une estimation, jamais une certitude : la fourchette indique l'incertitude du modèle."
      action={
        <Bouton variante="secondaire" onClick={() => void charger()} disabled={chargement}>
          {chargement ? "Calcul…" : "Actualiser"}
        </Bouton>
      }
    >
      <div className="flex flex-col gap-4">
        {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}

        {chargement ? (
          <Chargement libelle="Calcul des probabilités…" />
        ) : indisponible ? (
          <div className="flex flex-col gap-2">
            <Alerte ton="info">{indisponible}</Alerte>
            <EtatVide>
              Ajoutez les résultats terminés des rencontres passées de ces deux équipes, puis
              actualisez l&apos;analyse. Le modèle refuse volontairement de produire une
              probabilité quand l&apos;historique est trop court.
            </EtatVide>
          </div>
        ) : prediction ? (
          <>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-texte-faible">
              <Badge ton={tonQualite(prediction.quality.level)}>
                Fiabilité {prediction.quality.label.toLowerCase()}
              </Badge>
              <span>
                {prediction.quality.matches_home} matchs {equipeDomicile} ·{" "}
                {prediction.quality.matches_away} matchs {equipeExterieur}
              </span>
              <span>·</span>
              <span>
                échantillon effectif{" "}
                {Math.min(
                  prediction.quality.effective_home,
                  prediction.quality.effective_away,
                ).toLocaleString("fr-FR", { maximumFractionDigits: 1 })}
              </span>
              <span>·</span>
              <span>{prediction.model_version}</span>
              <span>·</span>
              <span>calculé le {formatDateHeure(prediction.computed_at)}</span>
            </div>

            {prediction.quality.warnings.length > 0 ? (
              <Alerte ton="avertissement">
                <ul className="list-disc space-y-1 pl-4">
                  {prediction.quality.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </Alerte>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-bordure bg-fond p-4">
                <p className="text-[11px] uppercase tracking-wide text-texte-faible">
                  Buts attendus · {equipeDomicile}
                </p>
                <p className="mt-1 font-mono text-2xl text-accent">
                  {prediction.expected_goals_home.toLocaleString("fr-FR", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </p>
              </div>
              <div className="rounded-xl border border-bordure bg-fond p-4">
                <p className="text-[11px] uppercase tracking-wide text-texte-faible">
                  Buts attendus · {equipeExterieur}
                </p>
                <p className="mt-1 font-mono text-2xl text-accent">
                  {prediction.expected_goals_away.toLocaleString("fr-FR", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </p>
              </div>
              <div className="rounded-xl border border-bordure bg-fond p-4">
                <p className="text-[11px] uppercase tracking-wide text-texte-faible">
                  Total attendu
                </p>
                <p className="mt-1 font-mono text-2xl text-texte">
                  {prediction.expected_goals_total.toLocaleString("fr-FR", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </p>
              </div>
            </div>

            <section>
              <h3 className="text-xs font-semibold text-texte">Résultat (1X2)</h3>
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                {prediction.resultat.map((selection) => (
                  <CarteSelection key={selection.code} selection={selection} accent />
                ))}
              </div>
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="text-xs font-semibold text-texte">Double chance</h3>
                <div className="mt-2 flex flex-col gap-2">
                  {prediction.double_chance.map((selection) => (
                    <CarteSelection key={selection.code} selection={selection} />
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-xs font-semibold text-texte">
                  Les deux équipes marquent
                </h3>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {prediction.btts.map((selection) => (
                    <CarteSelection key={selection.code} selection={selection} />
                  ))}
                </div>
              </div>
            </section>

            <section>
              <h3 className="text-xs font-semibold text-texte">Totaux de buts</h3>
              <div className="mt-2 flex flex-col gap-2">
                {prediction.totaux.map((total) => (
                  <div key={total.line} className="grid gap-2 sm:grid-cols-2">
                    <CarteSelection selection={total.over} />
                    <CarteSelection selection={total.under} />
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className="text-xs font-semibold text-texte">Scores exacts les plus probables</h3>
              <div className="mt-2 flex flex-wrap gap-2">
                {prediction.scores_exacts.map((score) => (
                  <span
                    key={score.label}
                    className="rounded-lg border border-bordure-forte bg-fond-eleve px-2.5 py-1.5 text-[11px] text-texte-doux"
                  >
                    <span className="font-mono text-texte">{score.label}</span> ·{" "}
                    {pourcent(score.probability, 1)}
                  </span>
                ))}
              </div>
            </section>

            <p className="text-[11px] text-texte-faible">
              {prediction.avertissement} Les fourchettes à 80 % proviennent d&apos;une
              simulation de l&apos;incertitude des forces estimées ; elles ne couvrent pas les
              événements imprévisibles (blessures, cartons, arbitrage).
            </p>
          </>
        ) : null}
      </div>
    </Panneau>
  );
}
