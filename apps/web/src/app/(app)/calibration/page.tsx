"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Alerte,
  Badge,
  Bouton,
  Champ,
  Chargement,
  EtatVide,
  Panneau,
  Selection,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import type { Calibration, TrancheCalibration } from "@/lib/types";

const limites = [20, 40, 60, 100];

function pourcent(valeur: number | null, signe = false): string {
  if (valeur === null) return "—";
  return `${(valeur * 100).toLocaleString("fr-FR", {
    signDisplay: signe ? "exceptZero" : "auto",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} %`;
}

function decimal(valeur: number | null, chiffres = 3): string {
  if (valeur === null) return "—";
  return valeur.toLocaleString("fr-FR", {
    minimumFractionDigits: chiffres,
    maximumFractionDigits: chiffres,
  });
}

function Indicateur({
  libelle,
  valeur,
  aide,
  ton = "texte",
}: {
  libelle: string;
  valeur: string;
  aide?: string;
  ton?: "succes" | "danger" | "texte" | "accent";
}) {
  const couleur =
    ton === "succes"
      ? "text-succes"
      : ton === "danger"
        ? "text-danger"
        : ton === "accent"
          ? "text-accent"
          : "text-texte";
  return (
    <div className="rounded-xl border border-bordure bg-fond p-4">
      <p className="text-[11px] text-texte-faible">{libelle}</p>
      <p className={`mt-1 font-mono text-lg ${couleur}`}>{valeur}</p>
      {aide ? <p className="mt-1 text-[10px] text-texte-faible">{aide}</p> : null}
    </div>
  );
}

function tonEcart(ecart: number): "danger" | "texte" {
  return Math.abs(ecart) > 0.02 ? "danger" : "texte";
}

function classeTon(ton: "danger" | "texte"): string {
  return ton === "danger" ? "text-danger" : "text-texte";
}

function BarreFiabilite({ tranche }: { tranche: TrancheCalibration }) {
  return (
    <div
      className="relative h-1.5 w-24 overflow-hidden rounded-full bg-fond-eleve"
      role="img"
      aria-label={`Probabilité moyenne ${pourcent(tranche.mean_predicted)}, fréquence observée ${pourcent(tranche.observed)}`}
    >
      <div
        className="absolute inset-y-0 left-0 bg-accent/30"
        style={{ width: `${Math.max(0, Math.min(100, tranche.observed * 100))}%` }}
      />
      <div
        className="absolute inset-y-0 w-0.5 bg-accent"
        style={{ left: `${Math.max(0, Math.min(100, tranche.mean_predicted * 100))}%` }}
      />
    </div>
  );
}

function LigneTranche({ tranche }: { tranche: TrancheCalibration }) {
  if (tranche.count === 0) {
    return (
      <tr className="border-b border-bordure/60 last:border-0">
        <td className="py-2 pr-3 font-mono text-texte-doux">
          {pourcent(tranche.low, false)} – {pourcent(tranche.high, false)}
        </td>
        <td className="py-2 pr-3 text-right font-mono text-texte-faible">0</td>
        <td className="py-2 pr-3 text-right font-mono text-texte-faible">—</td>
        <td className="py-2 pr-3 text-right font-mono text-texte-faible">—</td>
        <td className="py-2 pr-3 font-mono text-texte-faible">—</td>
        <td className="py-2 text-texte-faible">Aucune prévision</td>
      </tr>
    );
  }

  const ecart = tranche.mean_predicted - tranche.observed;
  return (
    <tr className="border-b border-bordure/60 last:border-0">
      <td className="py-2 pr-3 font-mono text-texte-doux">
        {pourcent(tranche.low, false)} – {pourcent(tranche.high, false)}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-texte">{tranche.count}</td>
      <td className="py-2 pr-3 text-right font-mono text-texte">
        {pourcent(tranche.mean_predicted)}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-texte">
        {pourcent(tranche.observed)}
      </td>
      <td className="py-2 pr-3 font-mono text-[10px] text-texte-doux">
        {pourcent(tranche.wilson_low)} – {pourcent(tranche.wilson_high)}
      </td>
      <td className={`py-2 pr-3 text-right font-mono ${classeTon(tonEcart(ecart))}`}>
        {pourcent(ecart, true)}
      </td>
      <td className="py-2">
        <BarreFiabilite tranche={tranche} />
      </td>
    </tr>
  );
}

export default function PageCalibration() {
  const [limite, setLimite] = useState(40);
  const [donnees, setDonnees] = useState<Calibration | null>(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);

  const charger = useCallback(async () => {
    setChargement(true);
    setErreur(null);
    try {
      const resultat = await apiFetch<Calibration>(
        `/v1/predictions/calibration?limit=${limite}`,
      );
      setDonnees(resultat);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setChargement(false);
    }
  }, [limite]);

  useEffect(() => {
    void charger();
  }, [charger]);

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Calibration du modèle</h1>
        <p className="mt-1 text-xs text-texte-doux">
          Rétro-test honnête : chaque rencontre passée est pronostiquée avec uniquement
          l&apos;historique antérieur à son coup d&apos;envoi, puis comparée au résultat réel.
          Cet outil mesure le modèle ; il ne garantit aucune performance future.
        </p>
      </header>

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}

      <Panneau
        titre="Paramètres du rétro-test"
        description="Le nombre de rencontres récentes évaluées est plafonné pour garder un calcul rapide."
        action={
          <Bouton onClick={() => void charger()} disabled={chargement}>
            {chargement ? "Calcul…" : "Actualiser"}
          </Bouton>
        }
      >
        <div className="max-w-xs">
          <Champ
            label="Rencontres évaluées au maximum"
            aide="Les rencontres sans historique suffisant sont exclues et comptées."
          >
            <Selection
              value={limite}
              onChange={(event) => setLimite(Number(event.target.value))}
              disabled={chargement}
            >
              {limites.map((valeur) => (
                <option key={valeur} value={valeur}>
                  {valeur} rencontres
                </option>
              ))}
            </Selection>
          </Champ>
        </div>
      </Panneau>

      {chargement ? (
        <Chargement libelle="Reconstruction des prévisions passées…" />
      ) : !donnees ? null : donnees.matches_evaluated === 0 ? (
        <Panneau titre="Résultat du rétro-test">
          <div className="flex flex-col gap-3">
            <Alerte ton="info">{donnees.message}</Alerte>
            <EtatVide>
              Saisissez des rencontres terminées avec leur score. Le modèle exige au moins
              trois matchs terminés par équipe avant chaque rencontre évaluée ; les autres
              sont exclues du calcul, jamais inventées.
            </EtatVide>
            {donnees.matches_excluded > 0 ? (
              <p className="text-[11px] text-texte-faible">
                {donnees.matches_excluded} rencontre(s) exclue(s) faute d&apos;historique
                suffisant.
              </p>
            ) : null}
          </div>
        </Panneau>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Indicateur
              libelle="Rencontres évaluées"
              valeur={String(donnees.matches_evaluated)}
              aide={`${donnees.matches_excluded} exclue(s) · ${donnees.home_wins} victoire(s) à domicile, ${donnees.draws} nul(s), ${donnees.away_wins} à l'extérieur`}
              ton="accent"
            />
            <Indicateur
              libelle="Score de Brier"
              valeur={decimal(donnees.brier)}
              aide="Plus bas est meilleur (0 = parfait)."
            />
            <Indicateur
              libelle="Log loss"
              valeur={decimal(donnees.log_loss)}
              aide="Pénalise les probabilités trop confiantes et fausses."
            />
            <Indicateur
              libelle="Précision"
              valeur={pourcent(donnees.accuracy)}
              aide="Part des rencontres où l'issue la plus probable s'est réalisée."
            />
            <Indicateur
              libelle="Compétence Brier"
              valeur={pourcent(donnees.brier_skill, true)}
              aide="Comparaison aux fréquences de base de l'échantillon. Positif = meilleur que la base."
              ton={
                donnees.brier_skill === null
                  ? "texte"
                  : donnees.brier_skill > 0
                    ? "succes"
                    : "danger"
              }
            />
            <Indicateur
              libelle="Erreur de calibration (ECE)"
              valeur={pourcent(donnees.ece)}
              aide="Écart moyen entre probabilité annoncée et fréquence observée."
            />
          </div>

          <Panneau
            titre="Tableau de fiabilité"
            description="Chaque probabilité 1X2 est rangée dans une tranche. La barre montre la fréquence observée ; le trait vertical indique la probabilité moyenne annoncée."
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse text-left text-[11px]">
                <thead>
                  <tr className="border-b border-bordure text-texte-faible">
                    <th className="pb-2 pr-3 font-medium">Tranche</th>
                    <th className="pb-2 pr-3 text-right font-medium">Effectif</th>
                    <th className="pb-2 pr-3 text-right font-medium">Probabilité moyenne</th>
                    <th className="pb-2 pr-3 text-right font-medium">Fréquence observée</th>
                    <th className="pb-2 pr-3 font-medium">Intervalle Wilson 95 %</th>
                    <th className="pb-2 pr-3 text-right font-medium">Écart</th>
                    <th className="pb-2 font-medium">Fiabilité</th>
                  </tr>
                </thead>
                <tbody>
                  {donnees.bins.map((tranche) => (
                    <LigneTranche key={`${tranche.low}-${tranche.high}`} tranche={tranche} />
                  ))}
                </tbody>
              </table>
            </div>
          </Panneau>

          <Panneau titre="Couverture et période">
            <div className="grid gap-3 text-[11px] text-texte-doux sm:grid-cols-3">
              <div className="rounded-lg border border-bordure bg-fond p-3">
                <p className="text-texte-faible">Période couverte</p>
                <p className="mt-1 text-texte">
                  {formatDateHeure(donnees.period_start)} →{" "}
                  {formatDateHeure(donnees.period_end)}
                </p>
              </div>
              <div className="rounded-lg border border-bordure bg-fond p-3">
                <p className="text-texte-faible">Couverture xG / tirs cadrés</p>
                <p className="mt-1 font-mono text-texte">
                  {pourcent(donnees.mean_xg_coverage)}
                </p>
              </div>
              <div className="rounded-lg border border-bordure bg-fond p-3">
                <p className="text-texte-faible">Version du modèle</p>
                <p className="mt-1 flex items-center gap-2 text-texte">
                  <Badge ton="accent">{donnees.model_version}</Badge>
                </p>
              </div>
            </div>
          </Panneau>

          <Alerte ton="avertissement">
            <p>{donnees.avertissement}</p>
            <p className="mt-1">
              Un échantillon faible ou une couverture xG partielle rendent ces indicateurs
              instables. La calibration décrit le passé du modèle, pas ses résultats futurs.
            </p>
          </Alerte>
        </>
      )}
    </div>
  );
}
