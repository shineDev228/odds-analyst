"use client";

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
import { formatDateHeure } from "@/lib/format";
import type {
  ApercuCalendrier,
  ApercuCotes,
  ApercuCsv,
  ApercuStatistiques,
  Competition,
  CompetitionDistante,
  CompteursSynchronisation,
  Equipe,
  EtatFournisseur,
  EvenementsCotes,
  Fournisseur,
  JournalSynchronisation,
  LienConnecteur,
  Page,
  Rencontre,
  ReponseStatistiques,
  ResultatApplication,
  Saison,
  VueConnecteurs,
} from "@/lib/types";
import { libellesFournisseur } from "@/lib/types";

interface FormLien {
  provider: Fournisseur;
  competition_id: string;
  season_id: string;
  external_league_id: string;
  external_season: string;
}

const formVide: FormLien = {
  provider: "bigballsdata",
  competition_id: "",
  season_id: "",
  external_league_id: "",
  external_season: "",
};

const BANDEAU =
  "Cotes 1xBet agrégées via The Odds API. Aucune cote inventée, aucune substitution " +
  "de bookmaker. Les marchés non fournis restent manuels (score exact, handicap).";

const routesDecouverte: Record<Fournisseur, string> = {
  bigballsdata: "/v1/connectors/bigballsdata/leagues",
  the_odds_api: "/v1/connectors/the-odds-api/sports",
  football_data: "/v1/connectors/football-data/competitions",
  football_data_uk: "/v1/connectors/football-data-uk/divisions",
};

function resumeCompteurs(compteurs: CompteursSynchronisation): string {
  return (
    `${compteurs.created} créée(s), ${compteurs.updated} mise(s) à jour, ` +
    `${compteurs.unchanged} inchangée(s), ${compteurs.conflicts} conflit(s), ` +
    `${compteurs.ignored} ignorée(s)`
  );
}

function Compteurs({ compteurs }: { compteurs: CompteursSynchronisation }) {
  const cases: Array<[string, number]> = [
    ["reçues", compteurs.received],
    ["créées", compteurs.created],
    ["mises à jour", compteurs.updated],
    ["inchangées", compteurs.unchanged],
    ["conflits", compteurs.conflicts],
    ["ignorées", compteurs.ignored],
  ];
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {cases.map(([libelle, valeur]) => (
        <div key={libelle} className="rounded-lg border border-bordure bg-fond px-3 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-texte-faible">{libelle}</dt>
          <dd className="mt-0.5 text-sm font-semibold text-texte">{valeur}</dd>
        </div>
      ))}
    </dl>
  );
}

function CarteFournisseur({ etat }: { etat: EtatFournisseur }) {
  const quota = etat.quota;
  const plafond = quota.limit ?? "—";
  return (
    <div className="rounded-xl border border-bordure bg-fond p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-texte">{etat.label}</p>
            {etat.provider === "football_data_uk" ? (
              <Badge ton="succes">Sans clé</Badge>
            ) : etat.configured ? (
              <Badge ton="succes">Clé configurée</Badge>
            ) : (
              <Badge ton="alerte">Clé absente</Badge>
            )}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-texte-faible">{etat.role}</p>
        </div>
        <a
          href={etat.documentation_url}
          target="_blank"
          rel="noreferrer"
          className="text-[11px] text-accent underline-offset-2 hover:underline"
        >
          Documentation
        </a>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded-lg border border-bordure bg-fond-eleve px-2.5 py-1.5">
          <p className="text-texte-faible">Quota</p>
          <p className="text-texte">
            {quota.used} / {plafond}
            {quota.remaining !== null ? ` · ${quota.remaining} restant(s)` : ""}
          </p>
        </div>
        <div className="rounded-lg border border-bordure bg-fond-eleve px-2.5 py-1.5">
          <p className="text-texte-faible">Dernière synchronisation</p>
          <p className="text-texte">{formatDateHeure(etat.last_sync_at)}</p>
        </div>
      </div>

      {etat.configured ? null : (
        <p className="mt-2 text-[11px] text-alerte">
          Renseignez la clé dans <code className="text-texte">.env</code> puis redémarrez l&apos;API.
          La page reste utilisable, la saisie manuelle reste disponible.
        </p>
      )}
    </div>
  );
}

export default function PageConnecteurs() {
  const [vue, setVue] = useState<VueConnecteurs | null>(null);
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [saisons, setSaisons] = useState<Saison[]>([]);
  const [journal, setJournal] = useState<JournalSynchronisation[]>([]);

  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);

  const [form, setForm] = useState<FormLien>(formVide);
  const [distantes, setDistantes] = useState<CompetitionDistante[]>([]);
  const [decouverte, setDecouverte] = useState(false);

  const [lienActif, setLienActif] = useState<string | null>(null);
  const [apercuCalendrier, setApercuCalendrier] = useState<ApercuCalendrier | null>(null);
  const [apercuStats, setApercuStats] = useState<ApercuStatistiques | null>(null);
  const [apercuCsv, setApercuCsv] = useState<ApercuCsv | null>(null);
  const [equipes, setEquipes] = useState<Equipe[]>([]);
  const [associationsCsv, setAssociationsCsv] = useState<Record<string, string>>({});
  const [selectionStats, setSelectionStats] = useState<string[]>([]);
  const [resultatStats, setResultatStats] = useState<ReponseStatistiques | null>(null);
  const [evenements, setEvenements] = useState<EvenementsCotes | null>(null);
  const [apercuCotes, setApercuCotes] = useState<ApercuCotes | null>(null);
  const [selectionEtendue, setSelectionEtendue] = useState<string[]>([]);
  const [apercuEtendu, setApercuEtendu] = useState<ApercuCotes | null>(null);
  const [matchs, setMatchs] = useState<Rencontre[]>([]);
  const [association, setAssociation] = useState<Record<string, string>>({});

  const lien = useMemo(
    () => vue?.links.find((item) => item.id === lienActif) ?? null,
    [vue, lienActif],
  );

  const charger = useCallback(async () => {
    const [vueChargee, pageCompetitions, runs] = await Promise.all([
      apiFetch<VueConnecteurs>("/v1/connectors"),
      apiFetch<Page<Competition>>("/v1/competitions?page_size=200"),
      apiFetch<JournalSynchronisation[]>("/v1/connectors/sync-runs?limit=20"),
    ]);
    setVue(vueChargee);
    setCompetitions(pageCompetitions.items);
    setJournal(runs);
  }, []);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        await charger();
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      } finally {
        if (actif) setChargement(false);
      }
    })();
    return () => {
      actif = false;
    };
  }, [charger]);

  function signalerSucces(message: string) {
    setSucces(message);
    setErreur(null);
    setTimeout(() => setSucces(null), 5000);
  }

  function reinitialiserActions() {
    setApercuCalendrier(null);
    setApercuStats(null);
    setApercuCsv(null);
    setEquipes([]);
    setAssociationsCsv({});
    setSelectionStats([]);
    setResultatStats(null);
    setEvenements(null);
    setApercuCotes(null);
    setSelectionEtendue([]);
    setApercuEtendu(null);
    setMatchs([]);
    setAssociation({});
  }

  function ouvrirLien(cible: LienConnecteur) {
    if (lienActif === cible.id) {
      setLienActif(null);
    } else {
      setLienActif(cible.id);
    }
    reinitialiserActions();
  }

  async function changerCompetition(competitionId: string) {
    setForm((courant) => ({ ...courant, competition_id: competitionId, season_id: "" }));
    setSaisons([]);
    if (!competitionId) return;
    try {
      const page = await apiFetch<Page<Saison>>(
        `/v1/seasons?competition_id=${competitionId}&page_size=200`,
      );
      setSaisons(page.items);
      setForm((courant) =>
        courant.season_id || page.items.length === 0
          ? courant
          : { ...courant, season_id: page.items[0].id },
      );
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function decouvrir() {
    setErreur(null);
    setDecouverte(true);
    setDistantes([]);
    try {
      const liste = await apiFetch<CompetitionDistante[]>(routesDecouverte[form.provider]);
      setDistantes(liste);
      if (liste.length === 0) {
        setErreur("Aucune compétition renvoyée par ce fournisseur.");
      }
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setDecouverte(false);
    }
  }

  async function creerLien(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    setErreur(null);
    if (!form.competition_id || !form.season_id) {
      setErreur("Choisissez une compétition et une saison internes.");
      return;
    }
    setAction("creation");
    try {
      await apiFetch<LienConnecteur>("/v1/connectors/links", {
        corps: {
          provider: form.provider,
          competition_id: form.competition_id,
          season_id: form.season_id,
          external_league_id: form.external_league_id.trim(),
          external_season: form.external_season.trim(),
          is_enabled: true,
        },
      });
      setForm((courant) => ({
        ...formVide,
        provider: courant.provider,
        competition_id: courant.competition_id,
        season_id: courant.season_id,
      }));
      setDistantes([]);
      await charger();
      signalerSucces("Lien de connecteur créé.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function basculerLien(cible: LienConnecteur) {
    setErreur(null);
    try {
      await apiFetch<LienConnecteur>(`/v1/connectors/links/${cible.id}`, {
        methode: "PATCH",
        corps: { is_enabled: !cible.is_enabled },
      });
      await charger();
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function supprimerLien(cible: LienConnecteur) {
    if (
      !window.confirm(
        `Supprimer le lien ${libellesFournisseur[cible.provider]} — ${cible.competition_name ?? "compétition inconnue"} ? ` +
          "Les rencontres et cotes déjà importées sont conservées.",
      )
    ) {
      return;
    }
    setErreur(null);
    try {
      await apiFetch<void>(`/v1/connectors/links/${cible.id}`, { methode: "DELETE" });
      if (lienActif === cible.id) {
        setLienActif(null);
        reinitialiserActions();
      }
      await charger();
      signalerSucces("Lien supprimé. Les données importées restent en base.");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function lancerApercuCalendrier(cible: LienConnecteur) {
    setErreur(null);
    setAction("calendrier");
    try {
      const resultat = await apiFetch<ApercuCalendrier>(
        `/v1/connectors/links/${cible.id}/fixtures/preview`,
        { methode: "POST" },
      );
      setApercuCalendrier(resultat);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function appliquer(runId: string, message: string) {
    setErreur(null);
    setAction(`apply-${runId}`);
    try {
      const resultat = await apiFetch<ResultatApplication>(
        `/v1/connectors/sync-runs/${runId}/apply`,
        { methode: "POST" },
      );
      await charger();
      setApercuCalendrier(null);
      setApercuCotes(null);
      setApercuEtendu(null);
      setEvenements(null);
      setApercuCsv(null);
      signalerSucces(`${message} ${resumeCompteurs(resultat.counts)}`);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function lancerApercuCsv(cible: LienConnecteur) {
    setErreur(null);
    setAction("csv");
    try {
      const resultat = await apiFetch<ApercuCsv>(
        `/v1/connectors/links/${cible.id}/csv/preview`,
        { methode: "POST" },
      );
      setApercuCsv(resultat);
      const inconnues = resultat.skipped.some((ligne) =>
        ligne.teams.some((equipe) => equipe.status !== "existing"),
      );
      if (inconnues) {
        await chargerEquipesCsv(cible);
      }
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function chargerEquipesCsv(cible: LienConnecteur) {
    const competition = competitions.find((item) => item.id === cible.competition_id);
    if (!competition) return;
    const page = await apiFetch<Page<Equipe>>(
      `/v1/teams?sport_id=${competition.sport_id}&page_size=200`,
    );
    setEquipes(page.items);
  }

  async function associerEquipeCsv(cible: LienConnecteur, externalId: string) {
    const teamId = associationsCsv[externalId];
    if (!teamId) {
      setErreur("Choisissez une équipe interne avant d'associer.");
      return;
    }
    setErreur(null);
    setAction(`csv-lien-${externalId}`);
    try {
      await apiFetch<void>(
        `/v1/connectors/football-data-uk/teams/link?link_id=${cible.id}`,
        { corps: { external_id: externalId, team_id: teamId } },
      );
      await lancerApercuCsv(cible);
      signalerSucces("Équipe associée durablement. L'aperçu a été relancé.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function chargerStats(cible: LienConnecteur) {
    setErreur(null);
    setAction("stats");
    setResultatStats(null);
    try {
      const resultat = await apiFetch<ApercuStatistiques>(
        `/v1/connectors/links/${cible.id}/stats/preview`,
        { methode: "POST" },
      );
      setApercuStats(resultat);
      setSelectionStats(resultat.candidates.slice(0, 10).map((item) => item.match_id));
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function appliquerStats(cible: LienConnecteur) {
    setErreur(null);
    setAction("stats-apply");
    try {
      const resultat = await apiFetch<ReponseStatistiques>(
        `/v1/connectors/links/${cible.id}/stats/apply`,
        { corps: { match_ids: selectionStats } },
      );
      setResultatStats(resultat);
      await charger();
      signalerSucces(
        `Statistiques : ${resultat.created} importée(s), ${resultat.conflicts} conflit(s), ` +
          `${resultat.ignored} ignorée(s).`,
      );
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function lancerEvenements(cible: LienConnecteur) {
    setErreur(null);
    setAction("evenements");
    try {
      const [resultat, pageMatchs] = await Promise.all([
        apiFetch<EvenementsCotes>(`/v1/connectors/links/${cible.id}/odds/events`, {
          methode: "POST",
        }),
        apiFetch<Page<Rencontre>>(`/v1/matches?season_id=${cible.season_id}&page_size=200`),
      ]);
      setEvenements(resultat);
      setMatchs(pageMatchs.items);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function associer(cible: LienConnecteur, eventId: string) {
    const matchId = association[eventId];
    if (!matchId) {
      setErreur("Choisissez une rencontre interne avant d'associer.");
      return;
    }
    setErreur(null);
    setAction(`associer-${eventId}`);
    try {
      await apiFetch<void>(
        `/v1/connectors/the-odds-api/events/${encodeURIComponent(eventId)}/link?link_id=${cible.id}`,
        { corps: { match_id: matchId } },
      );
      await lancerEvenements(cible);
      signalerSucces("Événement associé à la rencontre interne.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function lancerApercuCotes(cible: LienConnecteur) {
    setErreur(null);
    setAction("cotes");
    try {
      const resultat = await apiFetch<ApercuCotes>(
        `/v1/connectors/links/${cible.id}/odds/preview`,
        { methode: "POST" },
      );
      setApercuCotes(resultat);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  async function lancerApercuEtendu(cible: LienConnecteur) {
    if (selectionEtendue.length === 0) {
      setErreur("Sélectionnez au moins une rencontre.");
      return;
    }
    setErreur(null);
    setAction("etendu");
    try {
      const resultat = await apiFetch<ApercuCotes>(
        `/v1/connectors/links/${cible.id}/odds/extended/preview`,
        { corps: { match_ids: selectionEtendue } },
      );
      setApercuEtendu(resultat);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setAction(null);
    }
  }

  function basculerSelection(valeur: string, courant: string[], setter: (v: string[]) => void) {
    setter(
      courant.includes(valeur)
        ? courant.filter((item) => item !== valeur)
        : [...courant, valeur],
    );
  }

  if (chargement) {
    return <Chargement libelle="Chargement des connecteurs…" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Connecteurs</h1>
        <p className="mt-1 text-xs text-texte-doux">
          Importez calendrier, résultats, statistiques et cotes 1xBet. Chaque import passe par un
          aperçu stocké : rien n&apos;est écrit sans votre validation. La saisie manuelle reste la
          priorité et n&apos;est jamais écrasée.
        </p>
      </header>

      <Alerte ton="info">{BANDEAU}</Alerte>

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      <Panneau
        titre="État des fournisseurs"
        description="Aucun champ de clé ici : les secrets restent dans le fichier .env du serveur."
        action={
          <Bouton variante="discret" onClick={() => void charger()}>
            Rafraîchir
          </Bouton>
        }
      >
        <div className="grid gap-3 lg:grid-cols-3">
          {(vue?.providers ?? []).map((etat) => (
            <CarteFournisseur key={etat.provider} etat={etat} />
          ))}
        </div>
      </Panneau>

      <Panneau
        titre="Assistant de lien"
        description="Associez une compétition interne à son identifiant chez le fournisseur."
      >
        <form onSubmit={creerLien} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Champ label="Fournisseur">
            <Selection
              value={form.provider}
              onChange={(e) => {
                setForm({ ...form, provider: e.target.value as Fournisseur, external_league_id: "" });
                setDistantes([]);
              }}
            >
              {(Object.keys(libellesFournisseur) as Fournisseur[]).map((code) => (
                <option key={code} value={code}>
                  {libellesFournisseur[code]}
                </option>
              ))}
            </Selection>
          </Champ>

          <Champ label="Compétition interne">
            <Selection
              required
              value={form.competition_id}
              onChange={(e) => void changerCompetition(e.target.value)}
            >
              <option value="">—</option>
              {competitions.map((competition) => (
                <option key={competition.id} value={competition.id}>
                  {competition.name}
                </option>
              ))}
            </Selection>
          </Champ>

          <Champ label="Saison interne">
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

          <Champ
            label="Identifiant externe"
            aide={
              form.provider === "the_odds_api"
                ? "Clé de sport The Odds API, par exemple soccer_france_ligue_one."
                : form.provider === "football_data_uk"
                  ? "Code de division du fichier : F1 (Ligue 1), F2 (Ligue 2), E0 (Premier League)…"
                  : "Identifiant de compétition du fournisseur."
            }
          >
            <div className="flex gap-2">
              <Saisie
                required
                maxLength={200}
                value={form.external_league_id}
                onChange={(e) => setForm({ ...form, external_league_id: e.target.value })}
                placeholder={
                  form.provider === "the_odds_api"
                    ? "soccer_france_ligue_one"
                    : form.provider === "football_data_uk"
                      ? "F1"
                      : "ligue-1"
                }
              />
              <Bouton type="button" onClick={() => void decouvrir()} disabled={decouverte}>
                {decouverte ? "…" : "Découvrir"}
              </Bouton>
            </div>
          </Champ>

          <Champ
            label="Saison externe"
            aide={
              form.provider === "football_data_uk"
                ? "Année de début de saison : 2026 pour la saison 2026-2027."
                : undefined
            }
          >
            <Saisie
              required
              maxLength={40}
              value={form.external_season}
              onChange={(e) => setForm({ ...form, external_season: e.target.value })}
              placeholder={form.provider === "football_data_uk" ? "2026" : "2025"}
            />
          </Champ>

          <div className="flex items-end">
            <Bouton
              type="submit"
              variante="principal"
              className="w-full py-2"
              disabled={action === "creation"}
            >
              {action === "creation" ? "Création…" : "Créer le lien"}
            </Bouton>
          </div>

          {distantes.length > 0 ? (
            <div className="sm:col-span-2 lg:col-span-3">
              <Champ label="Compétitions trouvées chez le fournisseur">
                <Selection
                  value=""
                  onChange={(e) => {
                    const choix = distantes.find((item) => item.external_id === e.target.value);
                    if (choix) {
                      setForm({ ...form, external_league_id: choix.external_id });
                    }
                  }}
                >
                  <option value="">Choisir…</option>
                  {distantes.map((item) => (
                    <option key={item.external_id} value={item.external_id}>
                      {item.name}
                      {item.country ? ` — ${item.country}` : ""} ({item.external_id})
                    </option>
                  ))}
                </Selection>
              </Champ>
            </div>
          ) : null}
        </form>
      </Panneau>

      <Panneau
        titre={`Compétitions suivies (${vue?.links.length ?? 0})`}
        description="Chaque lien garde ses données si vous le supprimez : rien n'est effacé côté rencontres."
      >
        {(vue?.links.length ?? 0) === 0 ? (
          <EtatVide>
            Aucun lien. Créez-en un ci-dessus, puis lancez un aperçu de calendrier.
          </EtatVide>
        ) : (
          <ul className="flex flex-col gap-3">
            {(vue?.links ?? []).map((cible) => (
              <li key={cible.id} className="rounded-xl border border-bordure bg-fond p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-texte">
                        {cible.competition_name ?? "Compétition inconnue"}
                        {cible.season_label ? ` · ${cible.season_label}` : ""}
                      </p>
                      <Badge ton="accent">{libellesFournisseur[cible.provider]}</Badge>
                      {cible.is_enabled ? (
                        <Badge ton="succes">Actif</Badge>
                      ) : (
                        <Badge ton="neutre">Désactivé</Badge>
                      )}
                    </div>
                    <p className="mt-0.5 text-[11px] text-texte-faible">
                      Externe : <code className="text-texte-doux">{cible.external_league_id}</code>{" "}
                      · saison {cible.external_season} · calendrier{" "}
                      {formatDateHeure(cible.last_fixtures_sync_at)} · stats{" "}
                      {formatDateHeure(cible.last_stats_sync_at)} · cotes{" "}
                      {formatDateHeure(cible.last_odds_sync_at)}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Bouton variante="principal" onClick={() => ouvrirLien(cible)}>
                      {lienActif === cible.id ? "Fermer" : "Gérer"}
                    </Bouton>
                    <Bouton variante="discret" onClick={() => void basculerLien(cible)}>
                      {cible.is_enabled ? "Désactiver" : "Activer"}
                    </Bouton>
                    <Bouton variante="danger" onClick={() => void supprimerLien(cible)}>
                      Supprimer
                    </Bouton>
                  </div>
                </div>

                {lienActif === cible.id && lien ? (
                  <div className="mt-4 flex flex-col gap-4 border-t border-bordure pt-4">
                    {cible.provider === "football_data_uk" ? null : (
                    <section>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-xs font-semibold text-texte">Calendrier et résultats</h3>
                        <Bouton
                          onClick={() => void lancerApercuCalendrier(cible)}
                          disabled={action === "calendrier" || !cible.is_enabled}
                        >
                          {action === "calendrier" ? "Lecture…" : "Aperçu du calendrier"}
                        </Bouton>
                      </div>
                      <p className="mt-1 text-[11px] text-texte-faible">
                        L&apos;aperçu ne modifie rien. Vérifiez les compteurs et les conflits avant
                        d&apos;appliquer.
                      </p>

                      {apercuCalendrier ? (
                        <div className="mt-3 flex flex-col gap-3">
                          {apercuCalendrier.warnings.map((warning) => (
                            <Alerte key={warning} ton="avertissement">
                              {warning}
                            </Alerte>
                          ))}
                          <Compteurs compteurs={apercuCalendrier.counts} />
                          {apercuCalendrier.teams_to_create.length > 0 ? (
                            <p className="text-[11px] text-texte-doux">
                              Équipes à créer :{" "}
                              {apercuCalendrier.teams_to_create
                                .map((equipe) => equipe.name)
                                .join(", ")}
                            </p>
                          ) : null}
                          {apercuCalendrier.conflicts.length > 0 ? (
                            <Alerte ton="avertissement">
                              Conflits signalés : {apercuCalendrier.conflicts.join(" · ")}
                            </Alerte>
                          ) : null}
                          <div className="flex flex-wrap items-center gap-2">
                            <Bouton
                              variante="principal"
                              onClick={() =>
                                void appliquer(
                                  apercuCalendrier.run_id,
                                  "Calendrier appliqué.",
                                )
                              }
                              disabled={action?.startsWith("apply-")}
                            >
                              Appliquer l&apos;aperçu
                            </Bouton>
                            <span className="text-[11px] text-texte-faible">
                              Expire le {formatDateHeure(apercuCalendrier.expires_at)}
                            </span>
                          </div>
                        </div>
                      ) : null}
                    </section>
                    )}

                    {cible.provider === "football_data_uk" ? (
                      <section className="border-t border-bordure pt-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="text-xs font-semibold text-texte">
                            Résultats et statistiques (fichier public)
                          </h3>
                          <Bouton
                            onClick={() => void lancerApercuCsv(cible)}
                            disabled={action === "csv" || !cible.is_enabled}
                          >
                            {action === "csv" ? "Téléchargement…" : "Aperçu du fichier"}
                          </Bouton>
                        </div>
                        <p className="mt-1 text-[11px] text-texte-faible">
                          Fichier complet de la division : xG, tirs, tirs cadrés, corners, cartons.
                          Aucune clé, aucun quota, aucune cote importée depuis ce fichier. Les
                          valeurs manuelles ne sont jamais écrasées.
                        </p>

                        {apercuCsv ? (
                          <div className="mt-3 flex flex-col gap-3">
                            {apercuCsv.warnings.map((warning) => (
                              <Alerte key={warning} ton="avertissement">
                                {warning}
                              </Alerte>
                            ))}
                            <Compteurs compteurs={apercuCsv.counts} />
                            <p className="text-[11px] text-texte-faible">
                              « créées » = rencontres complétées par des statistiques · « mises à
                              jour » = résultats corrigés · « conflits » = valeurs déjà présentes,
                              conservées · « ignorées » = rencontres hors du calendrier interne.
                            </p>

                            {apercuCsv.skipped.length > 0 ? (
                              <div className="rounded-lg border border-bordure bg-fond-eleve p-3">
                                <p className="text-[11px] font-semibold text-texte">
                                  Lignes non importées ({apercuCsv.skipped.length})
                                </p>
                                <ul className="mt-2 flex max-h-72 flex-col gap-2 overflow-auto pr-1">
                                  {apercuCsv.skipped.map((ligne) => (
                                    <li
                                      key={`${ligne.label}-${ligne.played_on}`}
                                      className="text-[11px] text-texte-doux"
                                    >
                                      <span className="text-texte">{ligne.label}</span> ·{" "}
                                      {ligne.played_on} · {ligne.reason}
                                      {ligne.teams
                                        .filter((equipe) => equipe.status !== "existing")
                                        .map((equipe) => (
                                          <div
                                            key={equipe.external_id}
                                            className="mt-1 flex flex-wrap items-center gap-2"
                                          >
                                            <code className="text-texte">{equipe.csv_name}</code>
                                            <Selection
                                              value={associationsCsv[equipe.external_id] ?? ""}
                                              onChange={(e) =>
                                                setAssociationsCsv({
                                                  ...associationsCsv,
                                                  [equipe.external_id]: e.target.value,
                                                })
                                              }
                                            >
                                              <option value="">Choisir une équipe…</option>
                                              {equipes.map((item) => (
                                                <option key={item.id} value={item.id}>
                                                  {item.name}
                                                </option>
                                              ))}
                                            </Selection>
                                            <Bouton
                                              variante="discret"
                                              onClick={() =>
                                                void associerEquipeCsv(cible, equipe.external_id)
                                              }
                                              disabled={action === `csv-lien-${equipe.external_id}`}
                                            >
                                              Associer
                                            </Bouton>
                                            {equipe.suggestions.length > 0 ? (
                                              <span className="text-texte-faible">
                                                Suggestions : {equipe.suggestions.join(", ")}
                                              </span>
                                            ) : null}
                                          </div>
                                        ))}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}

                            <div className="flex flex-wrap items-center gap-2">
                              <Bouton
                                variante="principal"
                                onClick={() =>
                                  void appliquer(
                                    apercuCsv.run_id,
                                    "Résultats et statistiques appliqués.",
                                  )
                                }
                                disabled={action?.startsWith("apply-")}
                              >
                                Appliquer l&apos;aperçu
                              </Bouton>
                              <span className="text-[11px] text-texte-faible">
                                Expire le {formatDateHeure(apercuCsv.expires_at)}
                              </span>
                            </div>
                          </div>
                        ) : null}
                      </section>
                    ) : null}

                    {cible.provider === "bigballsdata" ? (
                      <section className="border-t border-bordure pt-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="text-xs font-semibold text-texte">
                            Statistiques manquantes
                          </h3>
                          <Bouton
                            onClick={() => void chargerStats(cible)}
                            disabled={action === "stats"}
                          >
                            {action === "stats" ? "Lecture…" : "Voir les rencontres"}
                          </Bouton>
                        </div>

                        {apercuStats ? (
                          <div className="mt-3 flex flex-col gap-3">
                            <p className="text-[11px] text-texte-doux">
                              {apercuStats.candidates.length} rencontre(s) terminée(s) sans
                              statistiques. Coût du lot : {apercuStats.cost} requête(s) · budget
                              restant {apercuStats.budget_remaining}.
                            </p>
                            {apercuStats.candidates.length === 0 ? (
                              <EtatVide>Aucune rencontre à compléter.</EtatVide>
                            ) : (
                              <>
                                <ul className="flex max-h-60 flex-col gap-1.5 overflow-auto pr-1">
                                  {apercuStats.candidates.map((candidat) => (
                                    <li
                                      key={candidat.match_id}
                                      className="flex items-center justify-between gap-2 rounded-lg border border-bordure/70 px-3 py-2"
                                    >
                                      <label className="flex items-center gap-2 text-xs text-texte">
                                        <input
                                          type="checkbox"
                                          checked={selectionStats.includes(candidat.match_id)}
                                          onChange={() =>
                                            basculerSelection(
                                              candidat.match_id,
                                              selectionStats,
                                              setSelectionStats,
                                            )
                                          }
                                        />
                                        {candidat.label}
                                      </label>
                                      <span className="text-[11px] text-texte-faible">
                                        {formatDateHeure(candidat.kickoff_at)}
                                      </span>
                                    </li>
                                  ))}
                                </ul>
                                <div className="flex flex-wrap items-center gap-2">
                                  <Bouton
                                    variante="principal"
                                    onClick={() => void appliquerStats(cible)}
                                    disabled={
                                      action === "stats-apply" ||
                                      selectionStats.length === 0 ||
                                      selectionStats.length > 10
                                    }
                                  >
                                    {action === "stats-apply"
                                      ? "Import…"
                                      : `Importer ${selectionStats.length} rencontre(s)`}
                                  </Bouton>
                                  <span className="text-[11px] text-texte-faible">
                                    Lot de 1 à 10. Les statistiques existantes sont conservées.
                                  </span>
                                </div>
                              </>
                            )}

                            {resultatStats ? (
                              <ul className="flex flex-col gap-1 text-[11px]">
                                {resultatStats.results.map((ligne) => (
                                  <li key={ligne.match_id} className="text-texte-doux">
                                    {ligne.status} · {ligne.message ?? "OK"}
                                  </li>
                                ))}
                              </ul>
                            ) : null}
                          </div>
                        ) : null}
                      </section>
                    ) : null}

                    {cible.provider === "the_odds_api" ? (
                      <>
                        <section className="border-t border-bordure pt-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <h3 className="text-xs font-semibold text-texte">
                              Appariement des événements
                            </h3>
                            <Bouton
                              onClick={() => void lancerEvenements(cible)}
                              disabled={action === "evenements"}
                            >
                              {action === "evenements" ? "Lecture…" : "Apparier (gratuit)"}
                            </Bouton>
                          </div>

                          {evenements ? (
                            <div className="mt-3 flex flex-col gap-3">
                              <p className="text-[11px] text-texte-doux">
                                {evenements.matched.length} événement(s) associé(s),{" "}
                                {evenements.unmatched.length} non associé(s). Bookmaker :{" "}
                                {evenements.bookmaker}.
                              </p>

                              {evenements.unmatched.length > 0 ? (
                                <ul className="flex flex-col gap-2">
                                  {evenements.unmatched.map((evenement) => (
                                    <li
                                      key={evenement.event_id}
                                      className="rounded-lg border border-alerte/30 bg-alerte/5 px-3 py-2"
                                    >
                                      <p className="text-xs text-texte">
                                        {evenement.home_team} — {evenement.away_team}
                                      </p>
                                      <p className="text-[11px] text-texte-faible">
                                        {formatDateHeure(evenement.commence_time)} ·{" "}
                                        {evenement.event_id}
                                      </p>
                                      <div className="mt-2 flex flex-wrap items-center gap-2">
                                        <Selection
                                          value={association[evenement.event_id] ?? ""}
                                          onChange={(e) =>
                                            setAssociation((courant) => ({
                                              ...courant,
                                              [evenement.event_id]: e.target.value,
                                            }))
                                          }
                                          className="max-w-md"
                                        >
                                          <option value="">Choisir une rencontre…</option>
                                          {matchs.map((rencontre) => (
                                            <option key={rencontre.id} value={rencontre.id}>
                                              {rencontre.home_team_name} —{" "}
                                              {rencontre.away_team_name} ·{" "}
                                              {formatDateHeure(rencontre.kickoff_at)}
                                            </option>
                                          ))}
                                        </Selection>
                                        <Bouton
                                          onClick={() => void associer(cible, evenement.event_id)}
                                          disabled={action === `associer-${evenement.event_id}`}
                                        >
                                          Associer
                                        </Bouton>
                                      </div>
                                    </li>
                                  ))}
                                </ul>
                              ) : null}
                            </div>
                          ) : null}
                        </section>

                        <section className="border-t border-bordure pt-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <h3 className="text-xs font-semibold text-texte">
                              Cotes principales (1X2, totaux)
                            </h3>
                            <Bouton
                              variante="principal"
                              onClick={() => void lancerApercuCotes(cible)}
                              disabled={action === "cotes"}
                            >
                              {action === "cotes" ? "Lecture…" : "Aperçu (2 crédits)"}
                            </Bouton>
                          </div>
                          <p className="mt-1 text-[11px] text-texte-faible">
                            Si 1xBet est absent : aucune cote importée, aucune substitution.
                          </p>

                          {apercuCotes ? (
                            <div className="mt-3 flex flex-col gap-3">
                              {apercuCotes.warnings.map((warning) => (
                                <Alerte key={warning} ton="avertissement">
                                  {warning}
                                </Alerte>
                              ))}
                              <Compteurs compteurs={apercuCotes.counts} />
                              <div className="flex flex-wrap items-center gap-2">
                                <Bouton
                                  variante="principal"
                                  onClick={() =>
                                    void appliquer(apercuCotes.run_id, "Cotes appliquées.")
                                  }
                                  disabled={action?.startsWith("apply-")}
                                >
                                  Appliquer les cotes
                                </Bouton>
                                <span className="text-[11px] text-texte-faible">
                                  Expire le {formatDateHeure(apercuCotes.expires_at)}
                                </span>
                              </div>
                            </div>
                          ) : null}
                        </section>

                        <section className="border-t border-bordure pt-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <h3 className="text-xs font-semibold text-texte">
                              Marchés étendus (double chance, BTTS)
                            </h3>
                            <Bouton
                              onClick={() => void lancerApercuEtendu(cible)}
                              disabled={action === "etendu" || selectionEtendue.length === 0}
                            >
                              {action === "etendu"
                                ? "Lecture…"
                                : `Aperçu (${selectionEtendue.length * 2} crédits)`}
                            </Bouton>
                          </div>
                          <p className="mt-1 text-[11px] text-texte-faible">
                            Sélectionnez jusqu&apos;à 20 événements déjà appariés. Coût : 2 crédits
                            par rencontre.
                          </p>

                          {evenements && evenements.matched.length > 0 ? (
                            <ul className="mt-3 flex max-h-60 flex-col gap-1.5 overflow-auto pr-1">
                              {evenements.matched.map((evenement) => (
                                <li
                                  key={evenement.event_id}
                                  className="flex items-center justify-between gap-2 rounded-lg border border-bordure/70 px-3 py-2"
                                >
                                  <label className="flex items-center gap-2 text-xs text-texte">
                                    <input
                                      type="checkbox"
                                      checked={selectionEtendue.includes(
                                        evenement.match_id ?? "",
                                      )}
                                      disabled={!evenement.match_id}
                                      onChange={() =>
                                        evenement.match_id
                                          ? basculerSelection(
                                              evenement.match_id,
                                              selectionEtendue,
                                              setSelectionEtendue,
                                            )
                                          : undefined
                                      }
                                    />
                                    {evenement.match_label ??
                                      `${evenement.home_team} — ${evenement.away_team}`}
                                  </label>
                                  <span className="text-[11px] text-texte-faible">
                                    {formatDateHeure(evenement.commence_time)}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mt-2 text-[11px] text-texte-faible">
                              Lancez d&apos;abord l&apos;appariement gratuit pour lister les
                              événements.
                            </p>
                          )}

                          {apercuEtendu ? (
                            <div className="mt-3 flex flex-col gap-3">
                              {apercuEtendu.warnings.map((warning) => (
                                <Alerte key={warning} ton="avertissement">
                                  {warning}
                                </Alerte>
                              ))}
                              <Compteurs compteurs={apercuEtendu.counts} />
                              <div className="flex flex-wrap items-center gap-2">
                                <Bouton
                                  variante="principal"
                                  onClick={() =>
                                    void appliquer(
                                      apercuEtendu.run_id,
                                      "Marchés étendus appliqués.",
                                    )
                                  }
                                  disabled={action?.startsWith("apply-")}
                                >
                                  Appliquer les marchés étendus
                                </Bouton>
                                <span className="text-[11px] text-texte-faible">
                                  Expire le {formatDateHeure(apercuEtendu.expires_at)}
                                </span>
                              </div>
                            </div>
                          ) : null}
                        </section>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panneau>

      <Panneau
        titre="Journal des synchronisations"
        description="Aperçus, applications et erreurs. Aucune clé n'est journalisée."
        action={
          <Bouton variante="discret" onClick={() => void charger()}>
            Rafraîchir
          </Bouton>
        }
      >
        {journal.length === 0 ? (
          <EtatVide>Aucune synchronisation enregistrée.</EtatVide>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-left text-[11px]">
              <thead>
                <tr className="text-texte-faible">
                  <th className="px-2 py-1.5 font-medium">Date</th>
                  <th className="px-2 py-1.5 font-medium">Fournisseur</th>
                  <th className="px-2 py-1.5 font-medium">Opération</th>
                  <th className="px-2 py-1.5 font-medium">Statut</th>
                  <th className="px-2 py-1.5 font-medium">Requêtes</th>
                  <th className="px-2 py-1.5 font-medium">Crédits</th>
                  <th className="px-2 py-1.5 font-medium">Détail</th>
                </tr>
              </thead>
              <tbody>
                {journal.map((run) => (
                  <tr key={run.id} className="border-t border-bordure/70">
                    <td className="px-2 py-1.5 text-texte-doux">
                      {formatDateHeure(run.created_at)}
                    </td>
                    <td className="px-2 py-1.5 text-texte-doux">
                      {libellesFournisseur[run.provider] ?? run.provider}
                    </td>
                    <td className="px-2 py-1.5 text-texte-doux">{run.operation}</td>
                    <td className="px-2 py-1.5">
                      <Badge
                        ton={
                          run.status === "applied"
                            ? "succes"
                            : run.status === "failed"
                              ? "danger"
                              : run.status === "expired"
                                ? "alerte"
                                : "neutre"
                        }
                      >
                        {run.status}
                      </Badge>
                    </td>
                    <td className="px-2 py-1.5 text-texte-doux">{run.requests_used}</td>
                    <td className="px-2 py-1.5 text-texte-doux">{run.credits_used}</td>
                    <td className="px-2 py-1.5 text-texte-faible">
                      {run.error_message ??
                        (typeof run.summary?.counts === "object"
                          ? JSON.stringify(run.summary.counts)
                          : "—")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panneau>

      <p className="text-[11px] leading-relaxed text-texte-faible">
        Les imports ne constituent ni une prédiction ni une garantie. Chaque cote reste une
        information incertaine, à confronter à votre propre analyse. Aucun pari n&apos;est placé
        automatiquement.
      </p>
    </div>
  );
}
