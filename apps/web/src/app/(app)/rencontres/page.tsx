"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Alerte,
  Badge,
  Bouton,
  Champ,
  Chargement,
  EtatVide,
  Panneau,
  Saisie,
  Selection,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { datetimeLocalParDefaut, formatDateHeure } from "@/lib/format";
import type {
  Competition,
  Equipe,
  Page,
  Rencontre,
  Saison,
  StatutRencontre,
} from "@/lib/types";
import { statutsRencontre } from "@/lib/types";

interface FormRencontre {
  competition_id: string;
  season_id: string;
  home_team_id: string;
  away_team_id: string;
  kickoff_at: string;
  venue: string;
  referee: string;
}

const formVide: FormRencontre = {
  competition_id: "",
  season_id: "",
  home_team_id: "",
  away_team_id: "",
  kickoff_at: "",
  venue: "",
  referee: "",
};

const tonsStatut: Record<StatutRencontre, "accent" | "succes" | "neutre" | "alerte" | "danger"> = {
  programme: "accent",
  en_cours: "alerte",
  termine: "succes",
  reporte: "neutre",
  annule: "danger",
};

export default function PageRencontres() {
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [equipes, setEquipes] = useState<Equipe[]>([]);
  const [saisons, setSaisons] = useState<Saison[]>([]);
  const [rencontres, setRencontres] = useState<Rencontre[]>([]);
  const [total, setTotal] = useState(0);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [form, setForm] = useState<FormRencontre>(formVide);

  const [filtreCompetition, setFiltreCompetition] = useState("");
  const [filtreStatut, setFiltreStatut] = useState("");
  const [ordre, setOrdre] = useState<"asc" | "desc">("desc");

  const competitionChoisie = useMemo(
    () => competitions.find((item) => item.id === form.competition_id) ?? null,
    [competitions, form.competition_id],
  );

  const equipesDisponibles = useMemo(() => {
    if (!competitionChoisie) return equipes;
    return equipes.filter((equipe) => equipe.sport_id === competitionChoisie.sport_id);
  }, [equipes, competitionChoisie]);

  const chargerRencontres = useCallback(
    async (competitionId: string, statut: string, sens: "asc" | "desc") => {
      const parametres = new URLSearchParams({ page_size: "200", order: sens });
      if (competitionId) parametres.set("competition_id", competitionId);
      if (statut) parametres.set("status", statut);
      const page = await apiFetch<Page<Rencontre>>(`/v1/matches?${parametres}`);
      setRencontres(page.items);
      setTotal(page.total);
    },
    [],
  );

  useEffect(() => {
    setForm((courant) =>
      courant.kickoff_at ? courant : { ...courant, kickoff_at: datetimeLocalParDefaut() },
    );
  }, []);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        const [listeCompetitions, pageEquipes] = await Promise.all([
          apiFetch<Page<Competition>>("/v1/competitions?page_size=200"),
          apiFetch<Page<Equipe>>("/v1/teams?page_size=200"),
        ]);
        if (!actif) return;
        setCompetitions(listeCompetitions.items);
        setEquipes(pageEquipes.items);
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      }
    })();
    return () => {
      actif = false;
    };
  }, []);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        await chargerRencontres(filtreCompetition, filtreStatut, ordre);
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      } finally {
        if (actif) setChargement(false);
      }
    })();
    return () => {
      actif = false;
    };
  }, [filtreCompetition, filtreStatut, ordre, chargerRencontres]);

  async function choisirCompetition(competitionId: string) {
    setForm((courant) => ({
      ...courant,
      competition_id: competitionId,
      season_id: "",
      home_team_id: "",
      away_team_id: "",
    }));
    setSaisons([]);
    if (!competitionId) return;
    try {
      const page = await apiFetch<Page<Saison>>(
        `/v1/seasons?competition_id=${competitionId}&page_size=200`,
      );
      setSaisons(page.items);
      setForm((courant) => ({
        ...courant,
        season_id: page.items[0]?.id ?? "",
      }));
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  function signalerSucces(message: string) {
    setSucces(message);
    setErreur(null);
    setTimeout(() => setSucces(null), 4000);
  }

  async function creer(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    setErreur(null);

    if (!form.season_id) {
      setErreur("Choisissez une compétition disposant d'au moins une saison.");
      return;
    }
    if (!form.home_team_id || !form.away_team_id) {
      setErreur("Sélectionnez les deux équipes.");
      return;
    }
    if (form.home_team_id === form.away_team_id) {
      setErreur("Les deux équipes doivent être différentes.");
      return;
    }

    setEnvoi(true);
    try {
      await apiFetch<Rencontre>("/v1/matches", {
        corps: {
          season_id: form.season_id,
          home_team_id: form.home_team_id,
          away_team_id: form.away_team_id,
          kickoff_at: form.kickoff_at ? new Date(form.kickoff_at).toISOString() : null,
          venue: form.venue.trim() || null,
          referee: form.referee.trim() || null,
        },
      });
      setForm({
        ...formVide,
        competition_id: form.competition_id,
        season_id: form.season_id,
        kickoff_at: datetimeLocalParDefaut(),
      });
      await chargerRencontres(filtreCompetition, filtreStatut, ordre);
      signalerSucces("Rencontre créée.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Rencontres</h1>
        <p className="mt-1 text-xs text-texte-doux">
          Saisissez vos rencontres, puis leurs statistiques et résultats.
        </p>
      </header>

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      <Panneau titre="Nouvelle rencontre">
        <form onSubmit={creer} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Champ label="Compétition">
            <Selection
              required
              value={form.competition_id}
              onChange={(e) => void choisirCompetition(e.target.value)}
            >
              <option value="">—</option>
              {competitions.map((competition) => (
                <option key={competition.id} value={competition.id}>
                  {competition.name}
                </option>
              ))}
            </Selection>
          </Champ>

          <Champ label="Saison">
            <Selection
              required
              value={form.season_id}
              onChange={(e) => setForm({ ...form, season_id: e.target.value })}
              disabled={saisons.length === 0}
            >
              <option value="">—</option>
              {saisons.map((saison) => (
                <option key={saison.id} value={saison.id}>
                  {saison.label}
                </option>
              ))}
            </Selection>
          </Champ>

          <Champ label="Équipe à domicile">
            <Selection
              required
              value={form.home_team_id}
              onChange={(e) => setForm({ ...form, home_team_id: e.target.value })}
            >
              <option value="">—</option>
              {equipesDisponibles.map((equipe) => (
                <option key={equipe.id} value={equipe.id}>
                  {equipe.name}
                </option>
              ))}
            </Selection>
          </Champ>

          <Champ label="Équipe à l'extérieur">
            <Selection
              required
              value={form.away_team_id}
              onChange={(e) => setForm({ ...form, away_team_id: e.target.value })}
            >
              <option value="">—</option>
              {equipesDisponibles.map((equipe) => (
                <option key={equipe.id} value={equipe.id}>
                  {equipe.name}
                </option>
              ))}
            </Selection>
          </Champ>

          <Champ label="Date et heure">
            <Saisie
              type="datetime-local"
              required
              value={form.kickoff_at}
              onChange={(e) => setForm({ ...form, kickoff_at: e.target.value })}
            />
          </Champ>

          <Champ label="Stade">
            <Saisie
              maxLength={120}
              value={form.venue}
              onChange={(e) => setForm({ ...form, venue: e.target.value })}
            />
          </Champ>

          <Champ label="Arbitre">
            <Saisie
              maxLength={120}
              value={form.referee}
              onChange={(e) => setForm({ ...form, referee: e.target.value })}
            />
          </Champ>

          <div className="flex items-end">
            <Bouton type="submit" variante="principal" disabled={envoi} className="w-full py-2">
              {envoi ? "Création…" : "Ajouter la rencontre"}
            </Bouton>
          </div>
        </form>

        {form.competition_id && saisons.length === 0 ? (
          <p className="mt-3 text-[11px] text-alerte">
            Cette compétition n&apos;a pas encore de saison.{" "}
            <Link href="/competitions" className="underline">
              Ajoutez-en une
            </Link>
            .
          </p>
        ) : null}
        {equipesDisponibles.length < 2 ? (
          <p className="mt-3 text-[11px] text-alerte">
            Il faut au moins deux équipes pour ce sport.{" "}
            <Link href="/equipes" className="underline">
              Créer des équipes
            </Link>
            .
          </p>
        ) : null}
      </Panneau>

      <Panneau
        titre={`Rencontres (${total})`}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Selection
              aria-label="Filtrer par compétition"
              value={filtreCompetition}
              onChange={(e) => setFiltreCompetition(e.target.value)}
              className="w-44"
            >
              <option value="">Toutes compétitions</option>
              {competitions.map((competition) => (
                <option key={competition.id} value={competition.id}>
                  {competition.name}
                </option>
              ))}
            </Selection>
            <Selection
              aria-label="Filtrer par statut"
              value={filtreStatut}
              onChange={(e) => setFiltreStatut(e.target.value)}
              className="w-36"
            >
              <option value="">Tous statuts</option>
              {Object.entries(statutsRencontre).map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>
                  {libelle}
                </option>
              ))}
            </Selection>
            <Selection
              aria-label="Ordre chronologique"
              value={ordre}
              onChange={(e) => setOrdre(e.target.value as "asc" | "desc")}
              className="w-32"
            >
              <option value="desc">Plus récentes</option>
              <option value="asc">Plus anciennes</option>
            </Selection>
          </div>
        }
      >
        {chargement ? (
          <Chargement />
        ) : rencontres.length === 0 ? (
          <EtatVide>Aucune rencontre ne correspond à ces critères.</EtatVide>
        ) : (
          <ul className="flex flex-col gap-2">
            {rencontres.map((rencontre) => (
              <li key={rencontre.id}>
                <Link
                  href={`/rencontres/${rencontre.id}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-bordure bg-fond p-3 transition hover:border-accent/40"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-texte">
                      {rencontre.home_team_name}{" "}
                      <span className="text-texte-faible">—</span>{" "}
                      {rencontre.away_team_name}
                    </p>
                    <p className="mt-0.5 truncate text-[11px] text-texte-faible">
                      {rencontre.competition_name} · {rencontre.season_label} ·{" "}
                      {formatDateHeure(rencontre.kickoff_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    {rencontre.home_score !== null || rencontre.away_score !== null ? (
                      <span className="font-mono text-sm text-texte">
                        {rencontre.home_score ?? "—"} : {rencontre.away_score ?? "—"}
                      </span>
                    ) : null}
                    <Badge ton={tonsStatut[rencontre.status]}>
                      {statutsRencontre[rencontre.status]}
                    </Badge>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panneau>
    </div>
  );
}
