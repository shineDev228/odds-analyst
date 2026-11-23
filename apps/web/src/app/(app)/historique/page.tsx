"use client";

import { useCallback, useEffect, useState } from "react";

import { BoiteDialogue } from "@/components/boite-dialogue";
import { useNotifications } from "@/components/notifications";
import {
  Alerte,
  Badge,
  Bouton,
  Chargement,
  EntetePage,
  EtatVide,
  Indicateur,
  Section,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import type {
  CombinaisonEnregistree,
  Page,
  ResumePerformance,
  StatutReglement,
} from "@/lib/types";

const TAILLE_PAGE = 20;

const filtres = [
  { code: "toutes", libelle: "Toutes" },
  { code: "en_attente", libelle: "En attente" },
  { code: "gagnee", libelle: "Gagnées" },
  { code: "perdue", libelle: "Perdues" },
  { code: "remboursee", libelle: "Remboursées" },
  { code: "indisponible", libelle: "Indisponibles" },
];

const tonsStatut: Record<
  StatutReglement,
  "succes" | "danger" | "alerte" | "accent" | "neutre"
> = {
  gagnee: "succes",
  perdue: "danger",
  remboursee: "accent",
  en_attente: "alerte",
  indisponible: "neutre",
};

function pourcent(valeur: number | null, signe = false): string {
  if (valeur === null) return "—";
  return `${(valeur * 100).toLocaleString("fr-FR", {
    signDisplay: signe ? "exceptZero" : "auto",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} %`;
}

function cote(valeur: number | null): string {
  if (valeur === null) return "—";
  return valeur.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function unites(valeur: number): string {
  return valeur.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function signeUnites(valeur: number | null): string {
  if (valeur === null) return "—";
  return `${valeur.toLocaleString("fr-FR", {
    signDisplay: "exceptZero",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} u`;
}

function tonNet(valeur: number): "succes" | "danger" | "texte" {
  if (valeur > 0) return "succes";
  if (valeur < 0) return "danger";
  return "texte";
}

function classeTon(ton: "succes" | "danger" | "texte"): string {
  if (ton === "succes") return "text-succes";
  if (ton === "danger") return "text-danger";
  return "text-texte";
}

function score(item: {
  home_score: number | null;
  away_score: number | null;
}): string {
  if (item.home_score === null || item.away_score === null) return "—";
  return `${item.home_score} - ${item.away_score}`;
}

function compteur(resume: ResumePerformance, code: string): number | null {
  if (code === "toutes") return resume.total;
  if (code === "en_attente") return resume.en_attente;
  if (code === "gagnee") return resume.gagnees;
  if (code === "perdue") return resume.perdues;
  if (code === "remboursee") return resume.remboursees;
  if (code === "indisponible") return resume.indisponibles;
  return null;
}

function CarteHistorique({
  item,
  onSupprimer,
  suppression,
}: {
  item: CombinaisonEnregistree;
  onSupprimer: () => void;
  suppression: boolean;
}) {
  const net = item.net_units;
  return (
    <article className="border-t border-bordure pt-4 first:border-0 first:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge ton={tonsStatut[item.status]}>{item.status_label}</Badge>
            <span className="text-xs text-texte-faible">
              {formatDateHeure(item.created_at)}
            </span>
            <span className="text-xs text-texte-faible">
              {item.nombre_selections} sélections
            </span>
          </div>
          <p className="mt-2 text-xs text-texte-faible">Cote totale</p>
          <p className="font-mono text-2xl tabular-nums text-texte">
            {cote(item.total_odds)}
          </p>
          {Math.abs(item.effective_odds - item.total_odds) > 1e-9 ? (
            <p className="mt-0.5 text-xs text-texte-faible">
              Cote effective <span className="font-mono">{cote(item.effective_odds)}</span>
            </p>
          ) : null}
          {item.note ? (
            <p className="mt-1 text-xs text-texte-faible">{item.note}</p>
          ) : null}
        </div>

        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-right text-xs">
          <span className="text-texte-faible">Probabilité estimée</span>
          <span className="font-mono text-texte">{pourcent(item.probability)}</span>
          <span className="text-texte-faible">Fourchette 80 %</span>
          <span className="font-mono text-texte-doux">
            {pourcent(item.low)} – {pourcent(item.high)}
          </span>
          <span className="text-texte-faible">Résultat (1 unité)</span>
          <span
            className={
              net === null
                ? "text-texte-faible"
                : `font-mono ${classeTon(tonNet(net))}`
            }
          >
            {signeUnites(net)}
          </span>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left">
          <thead>
            <tr className="border-b border-bordure text-[11px] text-texte-faible">
              <th className="pb-2 pr-3 font-medium">Rencontre</th>
              <th className="pb-2 pr-3 font-medium">Marché</th>
              <th className="pb-2 pr-3 font-medium">Choix</th>
              <th className="pb-2 pr-3 text-right font-medium">Cote</th>
              <th className="pb-2 pr-3 font-medium">Statut</th>
              <th className="pb-2 text-right font-medium">Score</th>
            </tr>
          </thead>
          <tbody>
            {item.selections.map((leg) => (
              <tr key={leg.id} className="border-b border-bordure/60 last:border-0">
                <td className="py-2 pr-3">
                  <p className="text-xs text-texte">{leg.match_label}</p>
                  <p className="text-[11px] text-texte-faible">
                    {leg.competition_name} · {formatDateHeure(leg.kickoff_at)}
                  </p>
                  <p className="mt-0.5 text-[11px] text-texte-faible">{leg.reason}</p>
                </td>
                <td className="py-2 pr-3 text-xs text-texte-doux">{leg.market_name}</td>
                <td className="py-2 pr-3 text-xs text-texte">{leg.selection_label}</td>
                <td className="py-2 pr-3 text-right font-mono text-xs tabular-nums text-texte">
                  {cote(leg.decimal_odds)}
                </td>
                <td className="py-2 pr-3">
                  <Badge ton={tonsStatut[leg.status]}>{leg.status_label}</Badge>
                </td>
                <td className="py-2 text-right font-mono text-xs tabular-nums text-texte-doux">
                  {score(leg)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex justify-end">
        <Bouton
          type="button"
          variante="discret"
          className="text-texte-faible hover:text-danger"
          onClick={onSupprimer}
          disabled={suppression}
        >
          {suppression ? "Suppression…" : "Supprimer"}
        </Bouton>
      </div>
    </article>
  );
}

export default function PageHistorique() {
  const [resume, setResume] = useState<ResumePerformance | null>(null);
  const [liste, setListe] = useState<Page<CombinaisonEnregistree> | null>(null);
  const [statut, setStatut] = useState("toutes");
  const [page, setPage] = useState(1);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [suppression, setSuppression] = useState<string | null>(null);
  const [aSupprimer, setASupprimer] = useState<CombinaisonEnregistree | null>(null);
  const { notifier } = useNotifications();

  const charger = useCallback(async (statutChoisi: string, numero: number) => {
    setChargement(true);
    setErreur(null);
    try {
      const [synthese, donnees] = await Promise.all([
        apiFetch<ResumePerformance>("/v1/combinations/performance"),
        apiFetch<Page<CombinaisonEnregistree>>(
          `/v1/combinations?page=${numero}&page_size=${TAILLE_PAGE}&statut=${statutChoisi}`,
        ),
      ]);
      setResume(synthese);
      setListe(donnees);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setChargement(false);
    }
  }, []);

  useEffect(() => {
    void charger(statut, page);
  }, [charger, statut, page]);

  function changerStatut(nouveau: string) {
    setStatut(nouveau);
    setPage(1);
  }

  async function supprimer() {
    if (!aSupprimer) return;
    setSuppression(aSupprimer.id);
    setErreur(null);
    try {
      await apiFetch<void>(`/v1/combinations/${aSupprimer.id}`, { methode: "DELETE" });
      notifier("succes", "Combinaison supprimée. La synthèse a été recalculée.");
      setASupprimer(null);
      await charger(statut, page);
    } catch (error) {
      setErreur(messageErreur(error));
      setASupprimer(null);
    } finally {
      setSuppression(null);
    }
  }

  if (chargement && !resume) {
    return <Chargement libelle="Chargement de l'historique…" />;
  }

  if (!resume) {
    return (
      <Alerte ton="erreur">
        {erreur ?? "Impossible de charger l'historique."}
      </Alerte>
    );
  }

  const totalPages = Math.max(1, Math.ceil((liste?.total ?? 0) / TAILLE_PAGE));

  return (
    <div className="flex flex-col gap-6">
      <EntetePage
        titre="Historique"
        description="Combinaisons enregistrées, règlement automatique et performance en unités de mise. Aucun montant en argent n'est utilisé."
      />

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}

      <Section
        titre="Synthèse de performance"
        description="Une unité par combinaison réglée. Les combinaisons en attente ou indisponibles sont exclues des calculs."
      >
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
          <Indicateur libelle="Enregistrées" valeur={String(resume.total)} />
          <Indicateur libelle="Réglées" valeur={String(resume.reglees)} />
          <Indicateur
            libelle="Taux de réussite"
            valeur={pourcent(resume.taux_reussite)}
            aide="Gagnées / (gagnées + perdues)"
          />
          <Indicateur
            libelle="Résultat net"
            valeur={signeUnites(resume.resultat_net)}
            ton={tonNet(resume.resultat_net)}
          />
          <Indicateur
            libelle="ROI"
            valeur={pourcent(resume.roi, true)}
            ton={
              resume.roi === null
                ? "texte"
                : resume.roi > 0
                  ? "succes"
                  : resume.roi < 0
                    ? "danger"
                    : "texte"
            }
          />
        </dl>

        <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-4 border-t border-bordure pt-4 sm:grid-cols-3 lg:grid-cols-6">
          <Indicateur libelle="Gagnées" valeur={String(resume.gagnees)} ton="succes" />
          <Indicateur libelle="Perdues" valeur={String(resume.perdues)} ton="danger" />
          <Indicateur libelle="En attente" valeur={String(resume.en_attente)} />
          <Indicateur libelle="Remboursées" valeur={String(resume.remboursees)} ton="accent" />
          <Indicateur libelle="Indisponibles" valeur={String(resume.indisponibles)} />
          <Indicateur libelle="Cote moyenne" valeur={cote(resume.cote_moyenne)} />
        </dl>

        <p className="mt-4 text-[11px] text-texte-faible">
          {unites(resume.unites_engagees)} unité(s) engagée(s) ·{" "}
          {unites(resume.unites_retournees)} unité(s) retournée(s).
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-texte-faible">
          {resume.avertissement}
        </p>
      </Section>

      <Section
        titre="Combinaisons enregistrées"
        description="Le statut est recalculé à chaque consultation à partir du score actuel des rencontres."
        action={
          chargement ? (
            <span className="text-xs text-texte-faible">Actualisation…</span>
          ) : undefined
        }
      >
        <div className="flex flex-wrap gap-1 border-b border-bordure">
          {filtres.map((filtre) => {
            const actif = statut === filtre.code;
            return (
              <button
                key={filtre.code}
                type="button"
                onClick={() => changerStatut(filtre.code)}
                aria-pressed={actif}
                className={`border-b-2 px-3 py-2 text-xs font-medium transition ${
                  actif
                    ? "border-accent text-accent"
                    : "border-transparent text-texte-doux hover:text-texte"
                }`}
              >
                {filtre.libelle}
                <span className="ml-1.5 font-mono text-[11px] text-texte-faible">
                  {compteur(resume, filtre.code)}
                </span>
              </button>
            );
          })}
        </div>

        <div className="mt-4 flex flex-col gap-4">
          {!liste || liste.items.length === 0 ? (
            <EtatVide>
              Aucune combinaison enregistrée pour ce filtre. Générez puis enregistrez une
              combinaison depuis la page Combinaisons.
            </EtatVide>
          ) : (
            liste.items.map((item) => (
              <CarteHistorique
                key={item.id}
                item={item}
                onSupprimer={() => setASupprimer(item)}
                suppression={suppression === item.id}
              />
            ))
          )}
        </div>

        {totalPages > 1 ? (
          <div className="mt-4 flex items-center justify-between gap-3 border-t border-bordure pt-3">
            <Bouton
              type="button"
              variante="secondaire"
              disabled={page <= 1 || chargement}
              onClick={() => setPage((courant) => Math.max(1, courant - 1))}
            >
              Précédent
            </Bouton>
            <span className="text-xs text-texte-faible">
              Page {page} / {totalPages}
            </span>
            <Bouton
              type="button"
              variante="secondaire"
              disabled={page >= totalPages || chargement}
              onClick={() => setPage((courant) => courant + 1)}
            >
              Suivant
            </Bouton>
          </div>
        ) : null}
      </Section>

      <BoiteDialogue
        ouvert={aSupprimer !== null}
        titre="Supprimer cette combinaison ?"
        description={
          aSupprimer
            ? `La combinaison du ${formatDateHeure(aSupprimer.created_at)} sera supprimée définitivement. La synthèse de performance sera recalculée.`
            : undefined
        }
        confirmation="Supprimer"
        enCours={suppression !== null}
        onConfirmer={() => void supprimer()}
        onAnnuler={() => setASupprimer(null)}
      />
    </div>
  );
}
