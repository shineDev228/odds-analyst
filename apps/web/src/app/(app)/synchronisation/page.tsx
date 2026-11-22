"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Alerte,
  Badge,
  Bouton,
  Champ,
  Chargement,
  EntetePage,
  EtatVide,
  Indicateur,
  Saisie,
  Section,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { formatDate, formatDateHeure, formatNombre } from "@/lib/format";
import type {
  ApercuCotes,
  JournalSynchronisation,
  LigueRapport,
  LigueRapportCotes,
  LigueRapportCsv,
  RapportCotes,
  RapportCsv,
  RapportSynchronisation,
  RapportTelechargementCsv,
  VueCotes,
  VueCsv,
  VueSynchronisation,
} from "@/lib/types";

const COMPETITIONS = [
  { code: "ligue1", libelle: "Ligue 1" },
  { code: "laliga", libelle: "La Liga" },
  { code: "epl", libelle: "Premier League" },
  { code: "seriea", libelle: "Serie A" },
  { code: "bundesliga", libelle: "Bundesliga" },
  { code: "ucl", libelle: "Ligue des champions" },
  { code: "mls", libelle: "MLS" },
] as const;

const TOUS = COMPETITIONS.map((item) => item.code);

const BANDEAU =
  "BigBallsData est la seule source des faits : calendrier, résultats, statistiques et " +
  "classements. Aucune équipe n'est appariée par son nom : l'identifiant du fournisseur est " +
  "stocké sur l'équipe et sur la rencontre. Une rencontre saisie à la main n'est jamais " +
  "modifiée. Le xG ne vient pas de BigBallsData : il sera ajouté par le fichier CSV.";

function tonStatut(statut: string | null): "succes" | "alerte" | "danger" | "neutre" {
  if (statut === "applied") return "succes";
  if (statut === "partial") return "alerte";
  if (statut === "failed") return "danger";
  return "neutre";
}

function libelleStatut(statut: string | null): string {
  if (statut === "applied") return "Appliquée";
  if (statut === "partial") return "Partielle";
  if (statut === "failed") return "Échec";
  if (statut === "skipped") return "Ignorée";
  if (statut === "empty") return "Rien à importer";
  return statut ?? "Jamais";
}

function compteur(run: JournalSynchronisation, cle: string): number | null {
  const compteurs = run.summary?.counts;
  if (!compteurs || typeof compteurs !== "object") return null;
  const valeur = (compteurs as Record<string, unknown>)[cle];
  return typeof valeur === "number" ? valeur : null;
}

function CarteRapport({ rapport }: { rapport: LigueRapport }) {
  return (
    <li className="border-b border-bordure/70 py-2 last:border-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs font-medium text-texte">{rapport.name}</p>
          <Badge ton={tonStatut(rapport.status)}>{libelleStatut(rapport.status)}</Badge>
        </div>
        <p className="text-xs text-texte-faible">
          {rapport.requests} requête(s) · {rapport.created} créée(s) · {rapport.updated} mise(s) à
          jour · {rapport.unchanged} inchangée(s) · {rapport.ignored} ignorée(s)
        </p>
      </div>
      {rapport.stats_written > 0 ||
      rapport.standings_written > 0 ||
      rapport.stats_missing > 0 ||
      rapport.duplicates > 0 ? (
        <p className="mt-1 text-xs text-texte-faible">
          Statistiques écrites : {rapport.stats_written}
          {rapport.stats_missing > 0 ? ` · sans statistiques : ${rapport.stats_missing}` : ""}
          {rapport.duplicates > 0 ? ` · fiches en double ignorées : ${rapport.duplicates}` : ""} · lignes
          de classement : {rapport.standings_written}
        </p>
      ) : null}
      {rapport.warnings.map((warning) => (
        <p key={warning} className="mt-1 text-xs text-alerte">
          {warning}
        </p>
      ))}
      {rapport.error ? <p className="mt-1 text-xs text-danger">{rapport.error}</p> : null}
    </li>
  );
}

const DECISIONS: Record<string, string> = {
  matched: "Rattaché",
  ambiguous: "Ambigu",
  unmatched: "Sans rencontre",
};

function tonDecision(decision: string): "succes" | "alerte" | "danger" | "neutre" {
  if (decision === "matched") return "succes";
  if (decision === "ambiguous") return "alerte";
  if (decision === "unmatched") return "danger";
  return "neutre";
}

function CarteRapportCotes({ rapport }: { rapport: LigueRapportCotes }) {
  return (
    <li className="border-b border-bordure/70 py-2 last:border-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs font-medium text-texte">{rapport.name}</p>
          <Badge ton={tonStatut(rapport.status)}>{libelleStatut(rapport.status)}</Badge>
        </div>
        <p className="text-xs text-texte-faible">
          {rapport.matched}/{rapport.events} rattachée(s) · {rapport.markets_written} marché(s) ·{" "}
          {rapport.snapshots_written} relevé(s) · {rapport.credits} crédit(s)
        </p>
      </div>
      <p className="mt-1 text-xs text-texte-faible">
        Liens créés : {rapport.links_created} · réutilisés : {rapport.links_reused} · désactivés :{" "}
        {rapport.links_deactivated} · sans 1xBet : {rapport.bookmaker_missing} · saisies manuelles
        conservées : {rapport.manual_kept}
      </p>
      {rapport.warnings.map((warning) => (
        <p key={warning} className="mt-1 text-xs text-alerte">
          {warning}
        </p>
      ))}
      {rapport.error ? <p className="mt-1 text-xs text-danger">{rapport.error}</p> : null}
    </li>
  );
}

function CarteRapportCsv({ rapport }: { rapport: LigueRapportCsv }) {
  return (
    <li className="border-b border-bordure/70 py-2 last:border-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs font-medium text-texte">{rapport.name}</p>
          <Badge ton={tonStatut(rapport.status)}>{libelleStatut(rapport.status)}</Badge>
        </div>
        <p className="text-xs text-texte-faible">
          {rapport.matched}/{rapport.rows} ligne(s) rattachée(s) · {rapport.xg_written} xG écrit(s) ·{" "}
          {rapport.snapshots_written} relevé(s) de clôture
        </p>
      </div>
      <p className="mt-1 text-xs text-texte-faible">
        Liens créés : {rapport.links_created} · réutilisés : {rapport.links_reused} · ambigus :{" "}
        {rapport.ambiguous} · sans rencontre : {rapport.unmatched} · xG déjà présent conservé :{" "}
        {rapport.xg_kept} · sans cotes complètes : {rapport.odds_missing} · saisies manuelles
        conservées : {rapport.manual_kept}
      </p>
      {rapport.warnings.map((warning) => (
        <p key={warning} className="mt-1 text-xs text-alerte">
          {warning}
        </p>
      ))}
      {rapport.error ? <p className="mt-1 text-xs text-danger">{rapport.error}</p> : null}
    </li>
  );
}

export default function PageSynchronisation() {
  const [vue, setVue] = useState<VueSynchronisation | null>(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const [selection, setSelection] = useState<string[]>([...TOUS]);
  const [avecStats, setAvecStats] = useState(true);
  const [avecClassement, setAvecClassement] = useState(true);
  const [limiteStats, setLimiteStats] = useState("20");
  const [rapport, setRapport] = useState<RapportSynchronisation | null>(null);
  const [cotes, setCotes] = useState<VueCotes | null>(null);
  const [apercu, setApercu] = useState<ApercuCotes | null>(null);
  const [rapportCotes, setRapportCotes] = useState<RapportCotes | null>(null);
  const [cotesEnCours, setCotesEnCours] = useState(false);
  const [avecEtendus, setAvecEtendus] = useState(true);
  const [limiteEtendus, setLimiteEtendus] = useState("30");
  const [csv, setCsv] = useState<VueCsv | null>(null);
  const [rapportCsv, setRapportCsv] = useState<RapportCsv | null>(null);
  const [telechargementCsv, setTelechargementCsv] =
    useState<RapportTelechargementCsv | null>(null);
  const [csvEnCours, setCsvEnCours] = useState(false);
  const [csvSansReseau, setCsvSansReseau] = useState(false);

  const charger = useCallback(async () => {
    const [donnees, etatCotes, etatCsv] = await Promise.all([
      apiFetch<VueSynchronisation>("/v1/sync/overview"),
      apiFetch<VueCotes>("/v1/sync/odds/overview"),
      apiFetch<VueCsv>("/v1/sync/csv/overview"),
    ]);
    setVue(donnees);
    setCotes(etatCotes);
    setCsv(etatCsv);
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

  function basculer(code: string) {
    setSelection((courant) =>
      courant.includes(code) ? courant.filter((item) => item !== code) : [...courant, code],
    );
  }

  function corpsCotes() {
    return {
      leagues: selection,
      include_extended: avecEtendus,
      extended_limit: Math.max(0, Math.min(30, Number(limiteEtendus) || 0)),
    };
  }

  async function apercuCotes() {
    if (selection.length === 0) {
      setErreur("Choisissez au moins une compétition.");
      return;
    }
    setErreur(null);
    setSucces(null);
    setCotesEnCours(true);
    try {
      const resultat = await apiFetch<ApercuCotes>("/v1/sync/odds/preview", {
        methode: "POST",
        corps: corpsCotes(),
        delaiMs: 180_000,
      });
      setApercu(resultat);
      const rattachees = resultat.leagues.reduce((total, ligue) => total + ligue.matched, 0);
      setSucces(
        `Aperçu terminé, aucun crédit consommé : ${rattachees} rencontre(s) rattachée(s), ` +
          `coût estimé ${resultat.credits_estimated} crédit(s).`,
      );
      await charger();
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setCotesEnCours(false);
    }
  }

  async function importerCotes() {
    if (selection.length === 0) {
      setErreur("Choisissez au moins une compétition.");
      return;
    }
    const estimation =
      apercu?.credits_estimated ??
      (cotes?.costs.competition ?? 2) * selection.length +
        (avecEtendus ? (cotes?.costs.event ?? 2) * Math.min(Number(limiteEtendus) || 0, 30) : 0);
    if (
      !window.confirm(
        `Importer les cotes 1xBet ? L'aperçu est gratuit, l'import consomme des crédits : ` +
          `environ ${estimation} crédit(s) pour cette passe. Les marchés saisis à la main ne ` +
          `seront pas modifiés.`,
      )
    ) {
      return;
    }
    setErreur(null);
    setSucces(null);
    setCotesEnCours(true);
    try {
      const resultat = await apiFetch<RapportCotes>("/v1/sync/odds/run", {
        methode: "POST",
        corps: corpsCotes(),
        delaiMs: 900_000,
      });
      setRapportCotes(resultat);
      await charger();
      setSucces(
        `Import des cotes ${libelleStatut(resultat.status).toLowerCase()} : ` +
          `${resultat.totals.matched ?? 0} rencontre(s) rattachée(s), ` +
          `${resultat.totals.markets_written ?? 0} marché(s), ` +
          `${resultat.credits_used} crédit(s) consommé(s).`,
      );
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setCotesEnCours(false);
    }
  }

  async function telechargerCsv() {
    setErreur(null);
    setSucces(null);
    setCsvEnCours(true);
    try {
      const resultat = await apiFetch<RapportTelechargementCsv>("/v1/sync/csv/download", {
        methode: "POST",
        corps: { leagues: selection },
        delaiMs: 180_000,
      });
      setTelechargementCsv(resultat);
      await charger();
      setSucces(
        `Téléchargement ${libelleStatut(resultat.status).toLowerCase()} : ` +
          `${resultat.totals.files ?? 0} fichier(s) conservé(s), ` +
          `${resultat.totals.rows ?? 0} rencontre(s) lue(s). Aucune donnée n'a été écrite en base.`,
      );
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setCsvEnCours(false);
    }
  }

  async function importerCsv() {
    const mode = csvSansReseau ? "les fichiers déjà téléchargés" : "les fichiers publics";
    if (
      !window.confirm(
        `Enrichir les rencontres terminées avec ${mode} ? Le xG ne remplace jamais une valeur ` +
          `déjà présente, les marchés saisis à la main restent intacts et une ligne douteuse ` +
          `n'écrit rien.`,
      )
    ) {
      return;
    }
    setErreur(null);
    setSucces(null);
    setCsvEnCours(true);
    try {
      const resultat = await apiFetch<RapportCsv>("/v1/sync/csv/run", {
        methode: "POST",
        corps: { leagues: selection, refresh: !csvSansReseau },
        delaiMs: 600_000,
      });
      setRapportCsv(resultat);
      await charger();
      const total = resultat.totals;
      setSucces(
        `Enrichissement ${libelleStatut(resultat.status).toLowerCase()} : ` +
          `${total.matched ?? 0} rencontre(s) rattachée(s), ${total.xg_written ?? 0} xG écrit(s), ` +
          `${total.snapshots_written ?? 0} relevé(s) de clôture, ` +
          `${total.ambiguous ?? 0} ligne(s) ambiguë(s).`,
      );
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setCsvEnCours(false);
    }
  }

  async function lancer() {
    if (selection.length === 0) {
      setErreur("Choisissez au moins une compétition.");
      return;
    }
    if (
      !window.confirm(
        "Lancer la synchronisation ? Les rencontres déjà connues seront mises à jour et les " +
          "nouvelles ajoutées. Une rencontre saisie à la main reste intacte.",
      )
    ) {
      return;
    }
    setErreur(null);
    setSucces(null);
    setEnCours(true);
    try {
      const resultat = await apiFetch<RapportSynchronisation>("/v1/sync/run", {
        methode: "POST",
        corps: {
          leagues: selection,
          include_stats: avecStats,
          include_standings: avecClassement,
          stats_limit: Math.max(0, Math.min(200, Number(limiteStats) || 0)),
        },
        // Une passe complète avec statistiques peut durer plusieurs minutes.
        delaiMs: 900_000,
      });
      setRapport(resultat);
      await charger();
      const total = resultat.totals;
      setSucces(
        `Synchronisation ${libelleStatut(resultat.status).toLowerCase()} : ` +
          `${total.created ?? 0} rencontre(s) créée(s), ${total.updated ?? 0} mise(s) à jour, ` +
          `${resultat.requests} requête(s) consommée(s).`,
      );
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnCours(false);
    }
  }

  if (chargement) {
    return <Chargement libelle="Lecture de l'état de la synchronisation…" />;
  }

  const quota = vue?.quota;
  const total = vue?.totals;

  return (
    <div className="flex flex-col gap-6">
      <EntetePage
        titre="Synchronisation"
        description="Une seule source de faits pour les sept compétitions suivies. Chaque passe est rejouable : relancer une journée déjà importée ne crée aucun doublon."
        action={
          <Bouton variante="secondaire" onClick={() => void charger()}>
            Rafraîchir
          </Bouton>
        }
      />

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      {vue && !vue.configured ? (
        <Alerte ton="avertissement">
          La clé BigBallsData est absente. Renseignez <code>BIGBALLSDATA_KEY</code> dans le fichier{" "}
          <code>.env</code> du serveur, puis redémarrez l&apos;API. La saisie manuelle reste
          disponible en attendant.
        </Alerte>
      ) : null}

      <Section
        titre="État"
        description="Compteur local, recalé sur les en-têtes du fournisseur. Un classement est enregistré une fois par jour et par équipe."
      >
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
          <Indicateur libelle="Requêtes utilisées" valeur={formatNombre(quota?.used)} />
          <Indicateur libelle="Restantes" valeur={formatNombre(quota?.remaining)} />
          <Indicateur libelle="Plafond local" valeur={formatNombre(quota?.limit)} />
          <Indicateur libelle="Réinitialisation" valeur={formatDateHeure(quota?.reset_at)} />
          <Indicateur libelle="Rencontres" valeur={formatNombre(total?.matches)} />
          <Indicateur libelle="Lignes avec xG" valeur={formatNombre(total?.xg_rows)} />
        </dl>
        <p className="mt-3 text-[11px] text-texte-faible">
          Saison demandée au fournisseur : {vue?.season ?? "—"}. Équipes du fournisseur :{" "}
          {formatNombre(total?.teams)} · lignes de statistiques : {formatNombre(total?.stats_rows)}.
        </p>
      </Section>

      <Section
      titre="Lancer une passe"
        description="Les données déjà présentes sont mises à jour, jamais dupliquées."
      >
        <fieldset className="flex flex-col gap-3">
          <legend className="text-xs text-texte-faible">
            Compétitions
          </legend>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {COMPETITIONS.map((competition) => (
              <label
                key={competition.code}
                className="flex items-center gap-2 text-xs text-texte"
              >
                <input
                  type="checkbox" className="size-4 accent-accent"
                  checked={selection.includes(competition.code)}
                  onChange={() => basculer(competition.code)}
                />
                {competition.libelle}
              </label>
            ))}
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="flex items-center gap-2 text-xs text-texte">
              <input
                type="checkbox" className="size-4 accent-accent"
                checked={avecStats}
                onChange={(event) => setAvecStats(event.target.checked)}
              />
              Statistiques des rencontres terminées
            </label>
            <label className="flex items-center gap-2 text-xs text-texte">
              <input
                type="checkbox" className="size-4 accent-accent"
                checked={avecClassement}
                onChange={(event) => setAvecClassement(event.target.checked)}
              />
              Classements du jour
            </label>
          </div>
          <Champ
            label="Limite de statistiques par compétition"
            aide="Chaque rencontre coûte une requête. Une limite garde la passe courte ; relancez-la pour continuer."
          >
            <Saisie
              type="number"
              min={0}
              max={200}
              value={limiteStats}
              onChange={(event) => setLimiteStats(event.target.value)}
            />
          </Champ>
          <Bouton
            variante="principal"
            onClick={() => void lancer()}
            disabled={enCours || !vue?.configured || selection.length === 0}
          >
            {enCours ? "Synchronisation en cours…" : "Synchroniser maintenant"}
          </Bouton>
          {enCours ? (
            <p className="text-xs text-texte-faible">
              La passe respecte un appel toutes les 0,8 seconde, soit 75 par minute : la limite
              du fournisseur est de 100 par minute. Laissez la page ouverte.
            </p>
          ) : null}
        </fieldset>
      </Section>

      <details className="border-t border-bordure pt-5">
        <summary className="cursor-pointer text-xs font-medium text-texte-doux">
          Fonctionnement de la source
        </summary>
        <p className="mt-3 max-w-[80ch] text-xs leading-relaxed text-texte-doux">{BANDEAU}</p>
      </details>

      {rapport ? (
        <Section
          titre="Résultat de la dernière passe"
          description={`${rapport.requests} requête(s) · quota restant ${rapport.quota_remaining ?? "—"}.`}
          action={
            <Badge ton={tonStatut(rapport.status)}>{libelleStatut(rapport.status)}</Badge>
          }
        >
          {rapport.error ? <Alerte ton="erreur">{rapport.error}</Alerte> : null}
          <ul className="mt-3 flex flex-col gap-2">
            {rapport.leagues.map((ligue) => (
              <CarteRapport key={ligue.code} rapport={ligue} />
            ))}
          </ul>
        </Section>
      ) : null}

      <Section
        titre="Cotes des rencontres à venir (1xBet)"
        description="The Odds API : aperçu gratuit, puis import payant dans le quota mensuel."
        action={
          <Badge ton={cotes?.configured ? "succes" : "danger"}>
            {cotes?.configured ? "Clé présente" : "Clé absente"}
          </Badge>
        }
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <dl className="flex flex-col gap-2 text-xs">
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Crédits restants</dt>
              <dd className="text-texte">{formatNombre(cotes?.quota.remaining)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Crédits utilisés ce mois</dt>
              <dd className="text-texte">{formatNombre(cotes?.quota.used)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Réinitialisation</dt>
              <dd className="text-texte">{formatDateHeure(cotes?.quota.reset_at)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Marchés cotés</dt>
              <dd className="text-texte">{formatNombre(cotes?.totals.markets)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Relevés de cotes</dt>
              <dd className="text-texte">{formatNombre(cotes?.totals.odds_rows)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Événements rattachés</dt>
              <dd className="text-texte">{formatNombre(cotes?.totals.active_links)}</dd>
            </div>
          </dl>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-xs text-texte-faible">
              Options d&apos;import
            </legend>
            <label className="flex items-center gap-2 text-xs text-texte">
              <input
                type="checkbox" className="size-4 accent-accent"
                checked={avecEtendus}
                onChange={(event) => setAvecEtendus(event.target.checked)}
              />
              Marchés étendus (double chance et les deux équipes marquent)
            </label>
            <Champ
              label="Plafond d'événements étendus"
              aide="Par passe, toutes compétitions confondues. Les marchés étendus ne sont demandés que pour les rencontres à moins de 72 heures."
            >
              <Saisie
                type="number"
                min={0}
                max={30}
                value={limiteEtendus}
                onChange={(event) => setLimiteEtendus(event.target.value)}
              />
            </Champ>
            <p className="text-xs text-texte-faible">
              Coût annoncé : {cotes?.costs.competition ?? 2} crédit(s) par compétition pour le 1X2 et
              les totaux, {cotes?.costs.event ?? 2} crédit(s) par événement étendu. L&apos;aperçu ne
              consomme rien.
            </p>
            <div className="flex flex-wrap gap-2">
              <Bouton
                variante="discret"
                onClick={() => void apercuCotes()}
                disabled={cotesEnCours || selection.length === 0}
              >
                {cotesEnCours ? "Traitement…" : "Aperçu gratuit"}
              </Bouton>
              <Bouton
                variante="principal"
                onClick={() => void importerCotes()}
                disabled={cotesEnCours || !cotes?.configured || selection.length === 0}
              >
                Importer les cotes
              </Bouton>
            </div>
          </fieldset>
        </div>

        {apercu ? (
          <div className="mt-4 flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-texte-doux">
                Coût estimé : <span className="font-medium text-texte">{apercu.credits_estimated}</span>{" "}
                crédit(s) · quota restant {apercu.quota_remaining ?? "—"}
              </p>
              <Badge ton={tonStatut(apercu.status)}>{libelleStatut(apercu.status)}</Badge>
            </div>
            {apercu.error ? <Alerte ton="erreur">{apercu.error}</Alerte> : null}
            <ul className="flex flex-col gap-2">
              {apercu.leagues.map((ligue) => (
                <li
                  key={ligue.code}
                  className="border-b border-bordure/70 py-2 last:border-0"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-medium text-texte">{ligue.name}</p>
                    <p className="text-xs text-texte-faible">
                      {ligue.matched}/{ligue.events} rattachée(s) · {ligue.ambiguous} ambigu(es) ·{" "}
                      {ligue.unmatched} sans rencontre · {ligue.credits} crédit(s)
                    </p>
                  </div>
                  {ligue.error ? (
                    <p className="mt-1 text-xs text-danger">{ligue.error}</p>
                  ) : null}
                  {ligue.items
                    .filter((item) => item.decision !== "matched")
                    .map((item) => (
                      <p key={item.event_id} className="mt-1 text-xs text-alerte">
                        {item.home_team} - {item.away_team} :{" "}
                        {DECISIONS[item.decision] ?? item.decision}
                        {item.method ? ` (${item.method})` : ""} — aucune cote ne sera écrite.
                      </p>
                    ))}
                  {ligue.items
                    .filter((item) => item.decision === "matched")
                    .slice(0, 5)
                    .map((item) => (
                      <p key={item.event_id} className="mt-1 text-xs text-texte-faible">
                        <Badge ton={tonDecision(item.decision)}>
                          {DECISIONS[item.decision] ?? item.decision}
                        </Badge>{" "}
                        {item.home_team} - {item.away_team}
                        {item.match_label ? ` → ${item.match_label}` : ""}
                      </p>
                    ))}
                  {ligue.matched > 5 ? (
                    <p className="mt-1 text-xs text-texte-faible">
                      … et {ligue.matched - 5} autre(s) rattachement(s) identique(s), non affiché(s).
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {rapportCotes ? (
          <div className="mt-4 flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-texte-doux">
                Dernier import : {rapportCotes.credits_used} crédit(s) ·{" "}
                {rapportCotes.requests} requête(s) · quota restant{" "}
                {rapportCotes.quota_remaining ?? "—"}
              </p>
              <Badge ton={tonStatut(rapportCotes.status)}>
                {libelleStatut(rapportCotes.status)}
              </Badge>
            </div>
            {rapportCotes.error ? <Alerte ton="erreur">{rapportCotes.error}</Alerte> : null}
            <ul className="flex flex-col gap-2">
              {rapportCotes.leagues.map((ligue) => (
                <CarteRapportCotes key={ligue.code} rapport={ligue} />
              ))}
            </ul>
          </div>
        ) : null}
      </Section>

      <Section
        titre="Enrichissement CSV (xG et cotes de clôture)"
        description="Fichiers publics football-data.co.uk : cinq compétitions, aucune clé, aucun quota."
        action={
          <Badge ton={(csv?.totals.files ?? 0) > 0 ? "succes" : "neutre"}>
            {csv?.totals.files ?? 0}/5 fichier(s)
          </Badge>
        }
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <dl className="flex flex-col gap-2 text-xs">
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Lignes CSV conservées</dt>
              <dd className="text-texte">{formatNombre(csv?.totals.rows)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Rencontres avec xG</dt>
              <dd className="text-texte">{formatNombre(csv?.totals.xg_rows)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Lignes rattachées</dt>
              <dd className="text-texte">{formatNombre(csv?.totals.links_applied)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Lignes en attente</dt>
              <dd className="text-texte">{formatNombre(csv?.totals.links_pending)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Marchés de clôture</dt>
              <dd className="text-texte">{formatNombre(csv?.totals.closing_markets)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Relevés de clôture</dt>
              <dd className="text-texte">{formatNombre(csv?.totals.closing_rows)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-texte-faible">Dernière passe</dt>
              <dd className="text-texte">{formatDateHeure(csv?.last_run?.created_at)}</dd>
            </div>
          </dl>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-xs text-texte-faible">
              Options d&apos;enrichissement
            </legend>
            <label className="flex items-center gap-2 text-xs text-texte">
              <input
                type="checkbox" className="size-4 accent-accent"
                checked={csvSansReseau}
                onChange={(event) => setCsvSansReseau(event.target.checked)}
              />
              Relire les fichiers déjà téléchargés, sans réseau
            </label>
            <p className="text-xs text-texte-faible">
              La rencontre est trouvée par son résultat : date exacte, score final et score à la
              mi-temps. Le nom ne sert qu&apos;à confirmer le sens domicile/extérieur. Sous une marge
              de 0,25 entre deux candidats, rien n&apos;est écrit : la ligne reste en attente.
            </p>
            <p className="text-xs text-texte-faible">
              Seule la moyenne du marché est enregistrée, sous le libellé « Clôture (moyenne) » et
              avec la source « csv ». Un xG déjà présent n&apos;est jamais remplacé. La Ligue des
              champions et la MLS ne publient pas de xG dans ces fichiers : elles restent hors
              périmètre.
            </p>
            <div className="flex flex-wrap gap-2">
              <Bouton
                variante="discret"
                onClick={() => void telechargerCsv()}
                disabled={csvEnCours || selection.length === 0}
              >
                {csvEnCours ? "Traitement…" : "Télécharger les fichiers"}
              </Bouton>
              <Bouton
                variante="principal"
                onClick={() => void importerCsv()}
                disabled={csvEnCours || selection.length === 0}
              >
                Enrichir xG et clôture
              </Bouton>
            </div>
            <p className="text-xs text-texte-faible">
              Dossier des fichiers : <code>{csv?.directory ?? "—"}</code>
            </p>
          </fieldset>
        </div>

        {(csv?.files.length ?? 0) > 0 ? (
          <ul className="mt-4 flex flex-col gap-2">
            {(csv?.files ?? []).map((fichier) => (
              <li
                key={fichier.code}
                className="border-b border-bordure/70 py-2 last:border-0"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-medium text-texte">{fichier.name}</p>
                    <Badge ton={fichier.stored ? "succes" : "neutre"}>
                      {fichier.stored ? `${fichier.rows} ligne(s)` : "Non téléchargé"}
                    </Badge>
                    {fichier.reused ? <Badge ton="alerte">Fichier local réutilisé</Badge> : null}
                  </div>
                  <p className="text-xs text-texte-faible">
                    {formatDateHeure(fichier.downloaded_at)} ·{" "}
                    {fichier.sha256 ? `empreinte ${fichier.sha256.slice(0, 12)}…` : "sans empreinte"}
                  </p>
                </div>
                {fichier.warnings.map((warning) => (
                  <p key={warning} className="mt-1 text-xs text-alerte">
                    {warning}
                  </p>
                ))}
                {fichier.error ? (
                  <p className="mt-1 text-xs text-danger">{fichier.error}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}

        {(csv?.coverage.length ?? 0) > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-xs">
              <thead>
                <tr className="border-b border-bordure text-left text-xs text-texte-faible">
                  <th className="px-2 py-1.5 font-medium">Compétition</th>
                  <th className="px-2 py-1.5 font-medium">Saison</th>
                  <th className="px-2 py-1.5 text-right font-medium">Terminées</th>
                  <th className="px-2 py-1.5 text-right font-medium">Avec xG</th>
                  <th className="px-2 py-1.5 text-right font-medium">Lignes appliquées</th>
                </tr>
              </thead>
              <tbody>
                {(csv?.coverage ?? []).map((ligne) => (
                  <tr key={ligne.code} className="border-b border-bordure/60">
                    <td className="px-2 py-1.5 text-texte">{ligne.name}</td>
                    <td className="px-2 py-1.5 text-texte-doux">{ligne.season_label ?? "—"}</td>
                    <td className="px-2 py-1.5 text-right text-texte">{ligne.finished}</td>
                    <td className="px-2 py-1.5 text-right text-texte">{ligne.covered}</td>
                    <td className="px-2 py-1.5 text-right text-texte">{ligne.links_applied}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {(csv?.pending.length ?? 0) > 0 ? (
          <div className="mt-4 flex flex-col gap-2">
            <p className="text-xs font-medium text-texte">Lignes en attente de décision</p>
            <ul className="flex flex-col gap-2">
              {(csv?.pending ?? []).map((ligne) => (
                <li
                  key={ligne.row_key}
                  className="border-b border-bordure/70 py-2 last:border-0"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs text-texte">
                      {ligne.label} · {ligne.competition}
                    </p>
                    <p className="text-xs text-texte-faible">
                      {formatDate(ligne.played_on)} · confiance{" "}
                      {ligne.confidence !== null ? ligne.confidence.toFixed(2) : "—"} · marge{" "}
                      {ligne.margin !== null ? ligne.margin.toFixed(2) : "—"}
                    </p>
                  </div>
                  {ligne.note ? (
                    <p className="mt-1 text-xs text-alerte">{ligne.note}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {telechargementCsv ? (
          <p className="mt-4 text-xs text-texte-faible">
            Dernier téléchargement : {telechargementCsv.totals.files ?? 0} fichier(s) ·{" "}
            {telechargementCsv.totals.rows ?? 0} rencontre(s) lue(s).{" "}
            {telechargementCsv.error ?? ""}
          </p>
        ) : null}

        {rapportCsv ? (
          <div className="mt-4 flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-texte-doux">
                Dernier enrichissement : {rapportCsv.totals.matched ?? 0} rencontre(s) rattachée(s) ·{" "}
                {rapportCsv.totals.xg_written ?? 0} xG écrit(s) ·{" "}
                {rapportCsv.totals.snapshots_written ?? 0} relevé(s)
              </p>
              <Badge ton={tonStatut(rapportCsv.status)}>
                {libelleStatut(rapportCsv.status)}
              </Badge>
            </div>
            {rapportCsv.error ? <Alerte ton="erreur">{rapportCsv.error}</Alerte> : null}
            <ul className="flex flex-col gap-2">
              {rapportCsv.leagues.map((ligue) => (
                <CarteRapportCsv key={ligue.code} rapport={ligue} />
              ))}
            </ul>
          </div>
        ) : null}
      </Section>

      <Section
        titre={`Compétitions suivies (${vue?.leagues.length ?? 0})`}
        description="Ce que la base contient pour chaque compétition, et la dernière passe connue."
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-xs">
            <thead>
              <tr className="border-b border-bordure text-left text-xs text-texte-faible">
                <th className="px-2 py-1.5 font-medium">Compétition</th>
                <th className="px-2 py-1.5 font-medium">Saison</th>
                <th className="px-2 py-1.5 text-right font-medium">Terminées</th>
                <th className="px-2 py-1.5 text-right font-medium">À venir</th>
                <th className="px-2 py-1.5 font-medium">Dernière passe</th>
                <th className="px-2 py-1.5 font-medium">État</th>
              </tr>
            </thead>
            <tbody>
              {(vue?.leagues ?? []).map((ligue) => (
                <tr key={ligue.code} className="border-b border-bordure/60">
                  <td className="px-2 py-1.5 text-texte">{ligue.name}</td>
                  <td className="px-2 py-1.5 text-texte-doux">{ligue.season_label ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right text-texte">{ligue.finished}</td>
                  <td className="px-2 py-1.5 text-right text-texte">{ligue.upcoming}</td>
                  <td className="px-2 py-1.5 text-texte-doux">
                    {formatDateHeure(ligue.last_sync_at)}
                  </td>
                  <td className="px-2 py-1.5">
                    <Badge ton={tonStatut(ligue.last_status)}>
                      {libelleStatut(ligue.last_status)}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        titre="Journal des passes"
        description="Une ligne par compétition et par passe. Aucune clé n'y figure."
      >
        {(vue?.runs.length ?? 0) === 0 ? (
          <EtatVide>Aucune synchronisation enregistrée pour le moment.</EtatVide>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-xs">
              <thead>
                <tr className="border-b border-bordure text-left text-xs text-texte-faible">
                  <th className="px-2 py-1.5 font-medium">Date</th>
                  <th className="px-2 py-1.5 font-medium">Compétition</th>
                  <th className="px-2 py-1.5 font-medium">État</th>
                  <th className="px-2 py-1.5 text-right font-medium">Requêtes</th>
                  <th className="px-2 py-1.5 text-right font-medium">Créées</th>
                  <th className="px-2 py-1.5 text-right font-medium">Mises à jour</th>
                  <th className="px-2 py-1.5 font-medium">Erreur</th>
                </tr>
              </thead>
              <tbody>
                {(vue?.runs ?? []).map((run) => (
                  <tr key={run.id} className="border-b border-bordure/60">
                    <td className="px-2 py-1.5 text-texte-doux">
                      {formatDateHeure(run.applied_at ?? run.created_at)}
                    </td>
                    <td className="px-2 py-1.5 text-texte">
                      {String((run.params as { league?: unknown }).league ?? "—")}
                    </td>
                    <td className="px-2 py-1.5">
                      <Badge ton={tonStatut(run.status)}>{libelleStatut(run.status)}</Badge>
                    </td>
                    <td className="px-2 py-1.5 text-right text-texte">{run.requests_used}</td>
                    <td className="px-2 py-1.5 text-right text-texte">
                      {compteur(run, "created") ?? "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right text-texte">
                      {compteur(run, "updated") ?? "—"}
                    </td>
                    <td className="px-2 py-1.5 text-xs text-danger">
                      {run.error_message ?? ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
