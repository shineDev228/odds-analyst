"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Combobox } from "@/components/combobox";
import { useNotifications } from "@/components/notifications";
import {
  Alerte,
  Bouton,
  Champ,
  Chargement,
  EntetePage,
  Panneau,
  Saisie,
  Selection,
} from "@/components/ui";
import { apiFetch, decrireErreur, messageErreur } from "@/lib/api";
import {
  datetimeLocalParDefaut,
  formatDateCourte,
  formatDateHeure,
  formatHeure,
} from "@/lib/format";
import { useGardeDepart } from "@/lib/use-garde-depart";
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

const TAILLE_PAGE = 50;

/** Statut affiché par défaut : les rencontres « programmées » d'abord. */
const STATUT_PAR_DEFAUT = "programme";

const couleursStatut: Record<StatutRencontre, string> = {
  programme: "bg-accent",
  en_cours: "bg-alerte",
  termine: "bg-succes",
  reporte: "bg-texte-faible",
  annule: "bg-danger",
};

function coteOuTiret(valeur: number | null): string {
  if (valeur === null) return "—";
  return valeur.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function indiceFavori(cotes: Rencontre["odds_1x2"]): number | null {
  if (!cotes) return null;
  const valeurs = [cotes.home, cotes.draw, cotes.away];
  let indice: number | null = null;
  let minimum = Number.POSITIVE_INFINITY;
  valeurs.forEach((valeur, index) => {
    if (valeur !== null && valeur < minimum) {
      minimum = valeur;
      indice = index;
    }
  });
  return indice;
}

function CelluleCote({ valeur, favori }: { valeur: number | null; favori: boolean }) {
  return (
    <td
      className={`px-1.5 py-2.5 text-right font-mono text-sm tabular-nums ${
        favori && valeur !== null ? "font-medium text-texte" : "text-texte-doux"
      }`}
    >
      {coteOuTiret(valeur)}
    </td>
  );
}

type ColonneTri = "date" | "home_team" | "score";

function EnTeteTriable({
  libelle,
  colonne,
  tri,
  ordre,
  onTri,
  className = "",
}: {
  libelle: string;
  colonne: ColonneTri;
  tri: ColonneTri;
  ordre: "asc" | "desc";
  onTri: (colonne: ColonneTri) => void;
  className?: string;
}) {
  const actif = tri === colonne;
  return (
    <th
      scope="col"
      aria-sort={actif ? (ordre === "asc" ? "ascending" : "descending") : undefined}
      className={className}
    >
      <button
        type="button"
        onClick={() => onTri(colonne)}
        className={`inline-flex items-center gap-1 font-medium transition hover:text-texte ${
          actif ? "text-texte" : ""
        }`}
      >
        {libelle}
        <span
          aria-hidden
          className={`text-[10px] leading-none ${actif ? "text-accent" : "text-texte-faible/50"}`}
        >
          {actif ? (ordre === "asc" ? "↑" : "↓") : "↕"}
        </span>
      </button>
    </th>
  );
}

export default function PageRencontres() {
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [equipes, setEquipes] = useState<Equipe[]>([]);
  const [saisons, setSaisons] = useState<Saison[]>([]);
  const [rencontres, setRencontres] = useState<Rencontre[]>([]);
  const [total, setTotal] = useState(0);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [erreursChamps, setErreursChamps] = useState<Record<string, string>>({});
  const [envoi, setEnvoi] = useState(false);
  const [form, setForm] = useState<FormRencontre>(formVide);
  const [formOuvert, setFormOuvert] = useState(false);

  const [filtreCompetition, setFiltreCompetition] = useState("");
  const [filtreEquipe, setFiltreEquipe] = useState("");
  const [filtreStatut, setFiltreStatut] = useState(STATUT_PAR_DEFAUT);
  const [ordre, setOrdre] = useState<"asc" | "desc">("asc");
  const [tri, setTri] = useState<ColonneTri>("date");
  const [page, setPage] = useState(1);
  const { notifier } = useNotifications();

  const filtreActif =
    filtreCompetition !== "" ||
    filtreEquipe !== "" ||
    filtreStatut !== STATUT_PAR_DEFAUT ||
    tri !== "date" ||
    ordre !== "asc";

  const viderErreurs = () => {
    setErreur(null);
    setErreursChamps({});
  };

  const competitionChoisie = useMemo(
    () => competitions.find((item) => item.id === form.competition_id) ?? null,
    [competitions, form.competition_id],
  );

  const equipesDisponibles = useMemo(() => {
    if (!competitionChoisie) return equipes;
    return equipes.filter((equipe) => equipe.sport_id === competitionChoisie.sport_id);
  }, [equipes, competitionChoisie]);

  const optionsEquipes = useMemo(
    () =>
      [...equipesDisponibles]
        .sort((a, b) => a.name.localeCompare(b.name, "fr"))
        .map((equipe) => ({ valeur: equipe.id, libelle: equipe.name })),
    [equipesDisponibles],
  );

  const optionsFiltreEquipes = useMemo(
    () =>
      [...equipes]
        .sort((a, b) => a.name.localeCompare(b.name, "fr"))
        .map((equipe) => ({ valeur: equipe.id, libelle: equipe.name })),
    [equipes],
  );

  const chargerRencontres = useCallback(
    async (
      competitionId: string,
      equipeId: string,
      statut: string,
      sens: "asc" | "desc",
      colonne: ColonneTri,
      numero: number,
    ) => {
      const parametres = new URLSearchParams({
        page_size: String(TAILLE_PAGE),
        page: String(numero),
        order: sens,
        sort: colonne,
      });
      if (competitionId) parametres.set("competition_id", competitionId);
      if (equipeId) parametres.set("team_id", equipeId);
      if (statut) parametres.set("status", statut);
      const pageRencontres = await apiFetch<Page<Rencontre>>(`/v1/matches?${parametres}`);
      setRencontres(pageRencontres.items);
      setTotal(pageRencontres.total);
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
        await chargerRencontres(
          filtreCompetition,
          filtreEquipe,
          filtreStatut,
          ordre,
          tri,
          page,
        );
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      } finally {
        if (actif) setChargement(false);
      }
    })();
    return () => {
      actif = false;
    };
  }, [filtreCompetition, filtreEquipe, filtreStatut, ordre, tri, page, chargerRencontres]);

  // Garde de départ : la date est pré-remplie et la saison choisie
  // automatiquement : on ignore ces champs pour ne pas avertir à tort.
  const saisieEnCours =
    formOuvert &&
    (form.competition_id !== "" ||
      form.home_team_id !== "" ||
      form.away_team_id !== "" ||
      form.venue.trim() !== "" ||
      form.referee.trim() !== "");
  useGardeDepart(saisieEnCours);

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
      const pageSaisons = await apiFetch<Page<Saison>>(
        `/v1/seasons?competition_id=${competitionId}&page_size=200`,
      );
      setSaisons(pageSaisons.items);
      setForm((courant) => ({
        ...courant,
        season_id: pageSaisons.items[0]?.id ?? "",
      }));
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  function reinitialiserFiltres() {
    setFiltreCompetition("");
    setFiltreEquipe("");
    setFiltreStatut(STATUT_PAR_DEFAUT);
    setOrdre("asc");
    setTri("date");
    setPage(1);
  }

  function basculerTri(colonne: ColonneTri) {
    if (tri === colonne) {
      setOrdre((courant) => (courant === "asc" ? "desc" : "asc"));
    } else {
      setTri(colonne);
      // Date : à venir d'abord (le plus proche) ; équipes : alphabétique ; score : décroissant.
      setOrdre(colonne === "score" ? "desc" : "asc");
    }
    setPage(1);
  }

  async function creer(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    viderErreurs();

    if (!form.season_id) {
      setErreursChamps({ season_id: "Choisissez une compétition disposant d'au moins une saison." });
      return;
    }
    if (!form.home_team_id || !form.away_team_id) {
      setErreursChamps({
        home_team_id: !form.home_team_id ? "Sélectionnez l'équipe à domicile." : "",
        away_team_id: !form.away_team_id ? "Sélectionnez l'équipe à l'extérieur." : "",
      });
      return;
    }
    if (form.home_team_id === form.away_team_id) {
      setErreursChamps({ away_team_id: "Les deux équipes doivent être différentes." });
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
      setFormOuvert(false);
      await chargerRencontres(filtreCompetition, filtreEquipe, filtreStatut, ordre, tri, page);
      notifier("succes", "Rencontre créée.");
    } catch (error) {
      const detail = decrireErreur(error);
      setErreur(detail.message);
      setErreursChamps(detail.champs);
    } finally {
      setEnvoi(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / TAILLE_PAGE));

  return (
    <div className="flex flex-col">
      <EntetePage
        titre="Rencontres"
        description="Calendrier, cotes 1X2 et résultats. Ouvrez une rencontre pour saisir ses statistiques et ses marchés."
        action={
          <Bouton
            variante={formOuvert ? "secondaire" : "principal"}
            onClick={() => setFormOuvert((ouvert) => !ouvert)}
            aria-expanded={formOuvert}
            aria-controls="nouvelle-rencontre"
          >
            {formOuvert ? "Fermer" : "Ajouter une rencontre"}
          </Bouton>
        }
      />

      {erreur ? (
        <div className="pb-4">
          <Alerte ton="erreur">{erreur}</Alerte>
        </div>
      ) : null}

      {formOuvert ? (
        <Panneau
          titre="Nouvelle rencontre"
          className="mb-5 scroll-mt-4"
          action={
            <Bouton variante="discret" onClick={() => setFormOuvert(false)}>
              Annuler
            </Bouton>
          }
        >
          <div id="nouvelle-rencontre">
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

              <Champ label="Saison" erreur={erreursChamps.season_id}>
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

              <Champ label="Équipe à domicile" erreur={erreursChamps.home_team_id}>
                <Combobox
                  nom="rencontre-domicile"
                  valeur={form.home_team_id}
                  onChange={(valeur) => setForm({ ...form, home_team_id: valeur })}
                  options={optionsEquipes}
                  placeholder="Rechercher une équipe…"
                  erreur={Boolean(erreursChamps.home_team_id)}
                />
              </Champ>

              <Champ label="Équipe à l'extérieur" erreur={erreursChamps.away_team_id}>
                <Combobox
                  nom="rencontre-exterieur"
                  valeur={form.away_team_id}
                  onChange={(valeur) => setForm({ ...form, away_team_id: valeur })}
                  options={optionsEquipes}
                  placeholder="Rechercher une équipe…"
                  erreur={Boolean(erreursChamps.away_team_id)}
                />
              </Champ>

              <Champ label="Date et heure" erreur={erreursChamps.kickoff_at}>
                <Saisie
                  type="datetime-local"
                  required
                  value={form.kickoff_at}
                  onChange={(e) => setForm({ ...form, kickoff_at: e.target.value })}
                />
              </Champ>

              <Champ label="Stade" erreur={erreursChamps.venue}>
                <Saisie
                  maxLength={120}
                  value={form.venue}
                  onChange={(e) => setForm({ ...form, venue: e.target.value })}
                />
              </Champ>

              <Champ label="Arbitre" erreur={erreursChamps.referee}>
                <Saisie
                  maxLength={120}
                  value={form.referee}
                  onChange={(e) => setForm({ ...form, referee: e.target.value })}
                />
              </Champ>

              <div className="flex items-end">
                <Bouton type="submit" variante="principal" disabled={envoi} className="w-full">
                  {envoi ? "Création…" : "Créer la rencontre"}
                </Bouton>
              </div>
            </form>

            {form.competition_id && saisons.length === 0 ? (
              <p className="mt-3 text-xs text-alerte">
                Cette compétition n&apos;a pas encore de saison.{" "}
                <Link href="/competitions" className="underline">
                  Ajoutez-en une
                </Link>
                .
              </p>
            ) : null}
            {equipesDisponibles.length < 2 ? (
              <p className="mt-3 text-xs text-alerte">
                Il faut au moins deux équipes pour ce sport.{" "}
                <Link href="/equipes" className="underline">
                  Créer des équipes
                </Link>
                .
              </p>
            ) : null}
          </div>
        </Panneau>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 border-y border-bordure py-3">
        <Selection
          aria-label="Filtrer par compétition"
          value={filtreCompetition}
          onChange={(e) => {
            setFiltreCompetition(e.target.value);
            setPage(1);
          }}
          className="sm:w-44"
        >
          <option value="">Toutes compétitions</option>
          {competitions.map((competition) => (
            <option key={competition.id} value={competition.id}>
              {competition.name}
            </option>
          ))}
        </Selection>
        <div className="sm:w-48">
          <Combobox
            nom="filtre-equipe"
            valeur={filtreEquipe}
            onChange={(valeur) => {
              setFiltreEquipe(valeur);
              setPage(1);
            }}
            options={optionsFiltreEquipes}
            placeholder="Toutes équipes…"
          />
        </div>
        <Selection
          aria-label="Filtrer par statut"
          value={filtreStatut}
          onChange={(e) => {
            setFiltreStatut(e.target.value);
            setPage(1);
          }}
          className="sm:w-36"
        >
          <option value="">Tous statuts</option>
          {Object.entries(statutsRencontre).map(([valeur, libelle]) => (
            <option key={valeur} value={valeur}>
              {libelle}
            </option>
          ))}
        </Selection>
        {filtreActif ? (
          <Bouton variante="discret" onClick={reinitialiserFiltres}>
            Réinitialiser
          </Bouton>
        ) : null}
        <span className="ml-auto text-xs text-texte-faible">
          {chargement
            ? "Chargement…"
            : `${total} rencontre${total > 1 ? "s" : ""}`}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] border-collapse text-left">
          <caption className="sr-only">
            Rencontres, avec leurs cotes 1X2, leur score et leur statut
          </caption>
          <thead>
            <tr className="border-b border-bordure-forte text-xs text-texte-faible">
              <EnTeteTriable
                libelle="Date"
                colonne="date"
                tri={tri}
                ordre={ordre}
                onTri={basculerTri}
                className="py-2 pr-3"
              />
              <EnTeteTriable
                libelle="Rencontre"
                colonne="home_team"
                tri={tri}
                ordre={ordre}
                onTri={basculerTri}
                className="py-2 pr-3"
              />
              <th scope="col" aria-label="Cote domicile" className="px-1.5 py-2 text-right font-medium">
                1
              </th>
              <th scope="col" aria-label="Cote match nul" className="px-1.5 py-2 text-right font-medium">
                X
              </th>
              <th scope="col" aria-label="Cote extérieur" className="px-1.5 py-2 text-right font-medium">
                2
              </th>
              <EnTeteTriable
                libelle="Score"
                colonne="score"
                tri={tri}
                ordre={ordre}
                onTri={basculerTri}
                className="py-2 pl-3 text-right"
              />
              <th scope="col" className="py-2 pl-3 font-medium">
                Statut
              </th>
            </tr>
          </thead>
          <tbody>
            {chargement ? (
              <tr>
                <td colSpan={7}>
                  <Chargement />
                </td>
              </tr>
            ) : rencontres.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center">
                  <p className="text-sm text-texte-doux">
                    Aucune rencontre ne correspond à ces critères.
                  </p>
                  {filtreActif ? (
                    <button
                      type="button"
                      onClick={reinitialiserFiltres}
                      className="mt-2 text-xs text-accent hover:underline"
                    >
                      Réinitialiser les filtres
                    </button>
                  ) : null}
                </td>
              </tr>
            ) : (
              rencontres.map((rencontre) => {
                const favori = indiceFavori(rencontre.odds_1x2);
                const aUnScore =
                  rencontre.home_score !== null || rencontre.away_score !== null;
                return (
                  <tr
                    key={rencontre.id}
                    className="group border-b border-bordure/70 transition-colors hover:bg-fond-panneau"
                  >
                    <td
                      className="whitespace-nowrap py-2.5 pr-3"
                      title={formatDateHeure(rencontre.kickoff_at)}
                    >
                      <span className="block text-xs text-texte-doux">
                        {formatDateCourte(rencontre.kickoff_at)}
                      </span>
                      <span className="block font-mono text-sm text-texte tabular-nums">
                        {formatHeure(rencontre.kickoff_at)}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3">
                      <Link href={`/rencontres/${rencontre.id}`} className="block">
                        <span className="block text-sm font-medium text-texte group-hover:text-accent">
                          {rencontre.home_team_name}{" "}
                          <span className="text-texte-faible">—</span>{" "}
                          {rencontre.away_team_name}
                        </span>
                        <span className="mt-0.5 block text-xs text-texte-faible">
                          {rencontre.competition_name} · {rencontre.season_label}
                        </span>
                      </Link>
                    </td>
                    <CelluleCote valeur={rencontre.odds_1x2?.home ?? null} favori={favori === 0} />
                    <CelluleCote valeur={rencontre.odds_1x2?.draw ?? null} favori={favori === 1} />
                    <CelluleCote valeur={rencontre.odds_1x2?.away ?? null} favori={favori === 2} />
                    <td
                      className={`py-2.5 pl-3 text-right font-mono text-sm tabular-nums ${
                        aUnScore ? "text-texte" : "text-texte-faible"
                      }`}
                    >
                      {aUnScore
                        ? `${rencontre.home_score ?? "—"} : ${rencontre.away_score ?? "—"}`
                        : "—"}
                    </td>
                    <td className="py-2.5 pl-3">
                      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-texte-doux">
                        <span
                          aria-hidden
                          className={`size-1.5 rounded-full ${couleursStatut[rencontre.status]}`}
                        />
                        {statutsRencontre[rencontre.status]}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
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
    </div>
  );
}
