"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  Alerte,
  Badge,
  Bouton,
  Champ,
  Chargement,
  Panneau,
  Saisie,
  Selection,
  ZoneTexte,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { formatDateHeure, versDatetimeLocal } from "@/lib/format";
import type { RencontreDetail, Statistique, StatutRencontre } from "@/lib/types";
import { statutsRencontre } from "@/lib/types";
import { PanneauMarches } from "@/components/match-markets";

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
  const [succes, setSucces] = useState<string | null>(null);
  const [edition, setEdition] = useState<FormEdition | null>(null);
  const [stats, setStats] = useState<Record<string, FormStats>>({});
  const [enregistrement, setEnregistrement] = useState(false);

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
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }, [id]);

  useEffect(() => {
    void charger();
  }, [charger]);

  function signalerSucces(message: string) {
    setSucces(message);
    setErreur(null);
    setTimeout(() => setSucces(null), 4000);
  }

  async function enregistrerEdition(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    if (!edition) return;
    setErreur(null);
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
      signalerSucces("Rencontre mise à jour.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnregistrement(false);
    }
  }

  async function enregistrerStats(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    if (!rencontre) return;
    setErreur(null);
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
      signalerSucces("Statistiques enregistrées.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnregistrement(false);
    }
  }

  async function supprimer() {
    if (!rencontre) return;
    if (!window.confirm("Supprimer définitivement cette rencontre et ses statistiques ?")) return;
    try {
      await apiFetch<void>(`/v1/matches/${id}`, { methode: "DELETE" });
      router.replace("/rencontres");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  function modifierStat(equipeId: string, cle: keyof FormStats, valeur: string) {
    setStats((courant) => ({
      ...courant,
      [equipeId]: { ...(courant[equipeId] ?? statsVide), [cle]: valeur },
    }));
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

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link href="/rencontres" className="text-[11px] text-texte-faible hover:text-accent">
          ← Rencontres
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              {rencontre.home_team_name} — {rencontre.away_team_name}
            </h1>
            <p className="mt-1 text-xs text-texte-doux">
              {rencontre.competition_name} · {rencontre.season_label} ·{" "}
              {formatDateHeure(rencontre.kickoff_at)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge ton={rencontre.status === "termine" ? "succes" : "accent"}>
              {statutsRencontre[rencontre.status]}
            </Badge>
            <Bouton variante="danger" onClick={() => void supprimer()}>
              Supprimer
            </Bouton>
          </div>
        </div>
      </div>

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      <Panneau titre="Informations et résultat">
        <form onSubmit={enregistrerEdition} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Champ label="Date et heure">
            <Saisie
              type="datetime-local"
              value={edition.kickoff_at}
              onChange={(e) => setEdition({ ...edition, kickoff_at: e.target.value })}
            />
          </Champ>
          <Champ label="Statut">
            <Selection
              value={edition.status}
              onChange={(e) =>
                setEdition({ ...edition, status: e.target.value as StatutRencontre })
              }
            >
              {Object.entries(statutsRencontre).map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>
                  {libelle}
                </option>
              ))}
            </Selection>
          </Champ>
          <Champ label="Stade">
            <Saisie
              maxLength={120}
              value={edition.venue}
              onChange={(e) => setEdition({ ...edition, venue: e.target.value })}
            />
          </Champ>
          <Champ label="Arbitre">
            <Saisie
              maxLength={120}
              value={edition.referee}
              onChange={(e) => setEdition({ ...edition, referee: e.target.value })}
            />
          </Champ>

          <Champ label={`Score ${rencontre.home_team_name}`}>
            <Saisie
              type="number"
              min={0}
              max={99}
              value={edition.home_score}
              onChange={(e) => setEdition({ ...edition, home_score: e.target.value })}
            />
          </Champ>
          <Champ label={`Score ${rencontre.away_team_name}`}>
            <Saisie
              type="number"
              min={0}
              max={99}
              value={edition.away_score}
              onChange={(e) => setEdition({ ...edition, away_score: e.target.value })}
            />
          </Champ>
          <Champ label="Mi-temps (domicile)">
            <Saisie
              type="number"
              min={0}
              max={99}
              value={edition.half_time_home_score}
              onChange={(e) => setEdition({ ...edition, half_time_home_score: e.target.value })}
            />
          </Champ>
          <Champ label="Mi-temps (extérieur)">
            <Saisie
              type="number"
              min={0}
              max={99}
              value={edition.half_time_away_score}
              onChange={(e) => setEdition({ ...edition, half_time_away_score: e.target.value })}
            />
          </Champ>

          <Champ label="Notes" className="sm:col-span-2 lg:col-span-4">
            <ZoneTexte
              maxLength={2000}
              value={edition.notes}
              onChange={(e) => setEdition({ ...edition, notes: e.target.value })}
            />
          </Champ>

          <div className="flex items-end sm:col-span-2 lg:col-span-4">
            <Bouton type="submit" variante="principal" disabled={enregistrement}>
              {enregistrement ? "Enregistrement…" : "Enregistrer la rencontre"}
            </Bouton>
          </div>
        </form>
      </Panneau>

      <Panneau
        titre="Statistiques d'équipe"
        description="Saisie manuelle. Laissez vide les valeurs inconnues : elles seront ignorées par le moteur."
      >
        <form onSubmit={enregistrerStats} className="flex flex-col gap-6">
          {[rencontre.home_team, rencontre.away_team].map((equipe) => {
            const equipeId = equipe.id;
            const valeurs = stats[equipeId] ?? statsVide;
            return (
              <div key={equipeId}>
                <h3 className="text-xs font-semibold text-texte">
                  {equipe.name}
                  <span className="ml-2 font-normal text-texte-faible">
                    {equipeId === rencontre.home_team_id ? "(domicile)" : "(extérieur)"}
                  </span>
                </h3>
                <div className="mt-2 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  {champsStats.map((champ) => (
                    <Champ key={champ.cle} label={champ.libelle}>
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
      </Panneau>

      <PanneauMarches
        matchId={rencontre.id}
        sportCode={rencontre.sport_code}
        equipeDomicile={rencontre.home_team}
        equipeExterieur={rencontre.away_team}
      />
    </div>
  );
}
