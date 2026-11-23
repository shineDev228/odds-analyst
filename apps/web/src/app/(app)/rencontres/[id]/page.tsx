"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { BoiteDialogue } from "@/components/boite-dialogue";
import { useNotifications } from "@/components/notifications";
import {
  Alerte,
  Badge,
  Bouton,
  Champ,
  Chargement,
  Saisie,
  Selection,
  ZoneTexte,
} from "@/components/ui";
import { apiFetch, decrireErreur, messageErreur } from "@/lib/api";
import { formatDateHeure, formatHeure, versDatetimeLocal } from "@/lib/format";
import { useGardeDepart } from "@/lib/use-garde-depart";
import type { RencontreDetail, Statistique, StatutRencontre } from "@/lib/types";
import { statutsRencontre } from "@/lib/types";
import { PanneauMarches } from "@/components/match-markets";
import { PanneauPrediction } from "@/components/match-prediction";

interface FormEdition {
  kickoff_at: string;
  status: StatutRencontre;
  home_score: string;
  away_score: string;
  half_time_home_score: string;
  half_time_away_score: string;
  venue: string;
  referee: string;
  notes: string;
}

interface FormStats {
  goals_for: string;
  goals_against: string;
  shots: string;
  shots_on_target: string;
  possession: string;
  corners: string;
  yellow_cards: string;
  red_cards: string;
  expected_goals: string;
}

const statsVide: FormStats = {
  goals_for: "",
  goals_against: "",
  shots: "",
  shots_on_target: "",
  possession: "",
  corners: "",
  yellow_cards: "",
  red_cards: "",
  expected_goals: "",
};

const champsStats: Array<{ cle: keyof FormStats; libelle: string; pas?: string }> = [
  { cle: "goals_for", libelle: "Buts pour" },
  { cle: "goals_against", libelle: "Buts contre" },
  { cle: "shots", libelle: "Tirs" },
  { cle: "shots_on_target", libelle: "Tirs cadrés" },
  { cle: "possession", libelle: "Possession (%)", pas: "0.1" },
  { cle: "corners", libelle: "Corners" },
  { cle: "yellow_cards", libelle: "Cartons jaunes" },
  { cle: "red_cards", libelle: "Cartons rouges" },
  { cle: "expected_goals", libelle: "Buts attendus (xG)", pas: "0.01" },
];

const couleursStatut: Record<StatutRencontre, "neutre" | "accent" | "succes" | "alerte" | "danger"> = {
  programme: "accent",
  en_cours: "alerte",
  termine: "succes",
  reporte: "neutre",
  annule: "danger",
};

function versFormStats(stat: Statistique | undefined): FormStats {
  if (!stat) return { ...statsVide };
  return {
    goals_for: stat.goals_for?.toString() ?? "",
    goals_against: stat.goals_against?.toString() ?? "",
    shots: stat.shots?.toString() ?? "",
    shots_on_target: stat.shots_on_target?.toString() ?? "",
    possession: stat.possession?.toString() ?? "",
    corners: stat.corners?.toString() ?? "",
    yellow_cards: stat.yellow_cards?.toString() ?? "",
    red_cards: stat.red_cards?.toString() ?? "",
    expected_goals: stat.expected_goals?.toString() ?? "",
  };
}

function nombreOuNull(valeur: string): number | null {
  if (valeur.trim() === "") return null;
  const nombre = Number(valeur.replace(",", "."));
  return Number.isFinite(nombre) ? nombre : null;
}

export default function PageRencontre() {
  const parametres = useParams<{ id: string }>();
  const router = useRouter();
  const id = parametres.id;

  const [rencontre, setRencontre] = useState<RencontreDetail | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [erreursChamps, setErreursChamps] = useState<Record<string, string>>({});
  const [edition, setEdition] = useState<FormEdition | null>(null);
  const [stats, setStats] = useState<Record<string, FormStats>>({});
  const [enregistrement, setEnregistrement] = useState(false);
  const [sale, setSale] = useState(false);
  const [confirmationSuppression, setConfirmationSuppression] = useState(false);
  const [suppression, setSuppression] = useState(false);
  const { notifier } = useNotifications();

  useGardeDepart(sale);

  const viderErreurs = () => {
    setErreur(null);
    setErreursChamps({});
  };

  const charger = useCallback(async () => {
    try {
      const donnees = await apiFetch<RencontreDetail>(`/v1/matches/${id}`);
      setRencontre(donnees);
      setEdition({
        kickoff_at: versDatetimeLocal(donnees.kickoff_at),
        status: donnees.status,
        home_score: donnees.home_score?.toString() ?? "",
        away_score: donnees.away_score?.toString() ?? "",
        half_time_home_score: donnees.half_time_home_score?.toString() ?? "",
        half_time_away_score: donnees.half_time_away_score?.toString() ?? "",
        venue: donnees.venue ?? "",
        referee: donnees.referee ?? "",
        notes: donnees.notes ?? "",
      });
      setStats({
        [donnees.home_team_id]: versFormStats(
          donnees.stats.find((item) => item.team_id === donnees.home_team_id),
        ),
        [donnees.away_team_id]: versFormStats(
          donnees.stats.find((item) => item.team_id === donnees.away_team_id),
        ),
      });
      setSale(false);
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }, [id]);

  useEffect(() => {
    void charger();
  }, [charger]);

  function majEdition(patch: Partial<FormEdition>) {
    setSale(true);
    setEdition((courant) => (courant ? { ...courant, ...patch } : courant));
  }

  function modifierStat(equipeId: string, cle: keyof FormStats, valeur: string) {
    setSale(true);
    setStats((courant) => ({
      ...courant,
      [equipeId]: { ...(courant[equipeId] ?? statsVide), [cle]: valeur },
    }));
  }

  async function enregistrerEdition(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    if (!edition) return;
    viderErreurs();
    setEnregistrement(true);
    try {
      await apiFetch<RencontreDetail>(`/v1/matches/${id}`, {
        methode: "PATCH",
        corps: {
          kickoff_at: edition.kickoff_at ? new Date(edition.kickoff_at).toISOString() : null,
          status: edition.status,
          home_score: nombreOuNull(edition.home_score),
          away_score: nombreOuNull(edition.away_score),
          half_time_home_score: nombreOuNull(edition.half_time_home_score),
          half_time_away_score: nombreOuNull(edition.half_time_away_score),
          venue: edition.venue.trim() || null,
          referee: edition.referee.trim() || null,
          notes: edition.notes.trim() || null,
        },
      });
      await charger();
      notifier("succes", "Rencontre mise à jour.");
    } catch (error) {
      const detail = decrireErreur(error);
      setErreur(detail.message);
      setErreursChamps(detail.champs);
    } finally {
      setEnregistrement(false);
    }
  }

  async function enregistrerStats(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    if (!rencontre) return;
    viderErreurs();
    setEnregistrement(true);
    try {
      const corps = [rencontre.home_team_id, rencontre.away_team_id].map((equipeId) => {
        const valeurs = stats[equipeId] ?? statsVide;
        return {
          team_id: equipeId,
          is_home: equipeId === rencontre.home_team_id,
          goals_for: nombreOuNull(valeurs.goals_for),
          goals_against: nombreOuNull(valeurs.goals_against),
          shots: nombreOuNull(valeurs.shots),
          shots_on_target: nombreOuNull(valeurs.shots_on_target),
          possession: nombreOuNull(valeurs.possession),
          corners: nombreOuNull(valeurs.corners),
          yellow_cards: nombreOuNull(valeurs.yellow_cards),
          red_cards: nombreOuNull(valeurs.red_cards),
          expected_goals: nombreOuNull(valeurs.expected_goals),
        };
      });
      await apiFetch(`/v1/matches/${id}/stats`, { methode: "PUT", corps });
      await charger();
      notifier("succes", "Statistiques enregistrées.");
    } catch (error) {
      const detail = decrireErreur(error);
      setErreur(detail.message);
      setErreursChamps(detail.champs);
    } finally {
      setEnregistrement(false);
    }
  }

  async function supprimer() {
    if (!rencontre) return;
    setSuppression(true);
    try {
      await apiFetch<void>(`/v1/matches/${id}`, { methode: "DELETE" });
      router.replace("/rencontres");
    } catch (error) {
      setErreur(messageErreur(error));
      setConfirmationSuppression(false);
    } finally {
      setSuppression(false);
    }
  }

  function erreurStat(equipeIndex: number, cle: keyof FormStats): string | undefined {
    return erreursChamps[`${equipeIndex}.${cle}`] ?? erreursChamps[cle];
  }

  if (erreur && !rencontre) {
    return (
      <div className="flex flex-col gap-4">
        <Alerte ton="erreur">{erreur}</Alerte>
        <Link href="/rencontres" className="text-xs text-accent hover:underline">
          ← Retour aux rencontres
        </Link>
      </div>
    );
  }

  if (!rencontre || !edition) return <Chargement />;

  const aUnScore = rencontre.home_score !== null || rencontre.away_score !== null;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/rencontres" className="text-xs text-texte-faible hover:text-accent">
          ← Rencontres
        </Link>

        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-2xl font-semibold tracking-tight">
              <span>{rencontre.home_team.name}</span>
              {aUnScore ? (
                <span className="font-mono text-3xl tabular-nums text-texte">
                  {rencontre.home_score ?? "—"} : {rencontre.away_score ?? "—"}
                </span>
              ) : (
                <span className="font-mono text-3xl tabular-nums text-texte-doux">
                  {formatHeure(rencontre.kickoff_at)}
                </span>
              )}
              <span>{rencontre.away_team.name}</span>
            </h1>
            <p className="mt-1 text-sm text-texte-doux">
              {rencontre.competition_name} · {rencontre.season_label} ·{" "}
              {formatDateHeure(rencontre.kickoff_at)}
            </p>
            {rencontre.venue || rencontre.referee ? (
              <p className="mt-0.5 text-xs text-texte-faible">
                {[rencontre.venue, rencontre.referee].filter(Boolean).join(" · ")}
              </p>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <Badge ton={couleursStatut[rencontre.status]}>
              {statutsRencontre[rencontre.status]}
            </Badge>
            <Bouton variante="danger" onClick={() => setConfirmationSuppression(true)}>
              Supprimer
            </Bouton>
          </div>
        </div>
      </header>

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}

      <PanneauPrediction
        matchId={rencontre.id}
        equipeDomicile={rencontre.home_team.name}
        equipeExterieur={rencontre.away_team.name}
      />

      <PanneauMarches
        matchId={rencontre.id}
        sportCode={rencontre.sport_code}
        equipeDomicile={rencontre.home_team}
        equipeExterieur={rencontre.away_team}
      />

      <details className="border-t border-bordure pt-5">
        <summary className="cursor-pointer text-base font-medium text-texte">
          Informations et résultat
        </summary>
        <form
          onSubmit={enregistrerEdition}
          className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        >
          <Champ label="Date et heure" erreur={erreursChamps.kickoff_at}>
            <Saisie
              type="datetime-local"
              value={edition.kickoff_at}
              onChange={(e) => majEdition({ kickoff_at: e.target.value })}
            />
          </Champ>
          <Champ label="Statut" erreur={erreursChamps.status}>
            <Selection
              value={edition.status}
              onChange={(e) => majEdition({ status: e.target.value as StatutRencontre })}
            >
              {Object.entries(statutsRencontre).map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>
                  {libelle}
                </option>
              ))}
            </Selection>
          </Champ>
          <Champ label="Stade" erreur={erreursChamps.venue}>
            <Saisie
              maxLength={120}
              value={edition.venue}
              onChange={(e) => majEdition({ venue: e.target.value })}
            />
          </Champ>
          <Champ label="Arbitre" erreur={erreursChamps.referee}>
            <Saisie
              maxLength={120}
              value={edition.referee}
              onChange={(e) => majEdition({ referee: e.target.value })}
            />
          </Champ>

          <Champ label={`Score ${rencontre.home_team.name}`} erreur={erreursChamps.home_score}>
            <Saisie
              type="number"
              min={0}
              max={99}
              value={edition.home_score}
              onChange={(e) => majEdition({ home_score: e.target.value })}
            />
          </Champ>
          <Champ label={`Score ${rencontre.away_team.name}`} erreur={erreursChamps.away_score}>
            <Saisie
              type="number"
              min={0}
              max={99}
              value={edition.away_score}
              onChange={(e) => majEdition({ away_score: e.target.value })}
            />
          </Champ>
          <Champ
            label="Mi-temps (domicile)"
            erreur={erreursChamps.half_time_home_score}
          >
            <Saisie
              type="number"
              min={0}
              max={99}
              value={edition.half_time_home_score}
              onChange={(e) => majEdition({ half_time_home_score: e.target.value })}
            />
          </Champ>
          <Champ
            label="Mi-temps (extérieur)"
            erreur={erreursChamps.half_time_away_score}
          >
            <Saisie
              type="number"
              min={0}
              max={99}
              value={edition.half_time_away_score}
              onChange={(e) => majEdition({ half_time_away_score: e.target.value })}
            />
          </Champ>

          <Champ label="Notes" className="sm:col-span-2 lg:col-span-4" erreur={erreursChamps.notes}>
            <ZoneTexte
              maxLength={2000}
              value={edition.notes}
              onChange={(e) => majEdition({ notes: e.target.value })}
            />
          </Champ>

          <div className="flex items-end sm:col-span-2 lg:col-span-4">
            <Bouton type="submit" variante="principal" disabled={enregistrement}>
              {enregistrement ? "Enregistrement…" : "Enregistrer la rencontre"}
            </Bouton>
          </div>
        </form>
      </details>

      <details className="border-t border-bordure pt-5">
        <summary className="cursor-pointer text-base font-medium text-texte">
          Statistiques d&apos;équipe
        </summary>
        <p className="mt-1 text-xs text-texte-doux">
          Saisie manuelle. Laissez vide les valeurs inconnues : elles seront ignorées par le
          moteur.
        </p>
        <form onSubmit={enregistrerStats} className="mt-4 flex flex-col gap-6">
          {[rencontre.home_team, rencontre.away_team].map((equipe, index) => {
            const equipeId = equipe.id;
            const valeurs = stats[equipeId] ?? statsVide;
            return (
              <div key={equipeId}>
                <h3 className="text-sm font-medium text-texte">
                  {equipe.name}
                  <span className="ml-2 font-normal text-texte-faible">
                    {equipeId === rencontre.home_team_id ? "(domicile)" : "(extérieur)"}
                  </span>
                </h3>
                <div className="mt-2 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  {champsStats.map((champ) => (
                    <Champ
                      key={champ.cle}
                      label={champ.libelle}
                      erreur={erreurStat(index, champ.cle)}
                    >
                      <Saisie
                        type="number"
                        min={0}
                        step={champ.pas ?? "1"}
                        value={valeurs[champ.cle]}
                        onChange={(e) => modifierStat(equipeId, champ.cle, e.target.value)}
                      />
                    </Champ>
                  ))}
                </div>
              </div>
            );
          })}

          <div>
            <Bouton type="submit" variante="principal" disabled={enregistrement}>
              {enregistrement ? "Enregistrement…" : "Enregistrer les statistiques"}
            </Bouton>
          </div>
        </form>
      </details>

      <BoiteDialogue
        ouvert={confirmationSuppression}
        titre="Supprimer cette rencontre ?"
        description="La rencontre et ses statistiques seront supprimées définitivement."
        confirmation="Supprimer"
        enCours={suppression}
        onConfirmer={() => void supprimer()}
        onAnnuler={() => setConfirmationSuppression(false)}
      />
    </div>
  );
}
