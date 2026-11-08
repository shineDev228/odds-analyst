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
import {
  descriptionMarche,
  libelleFamille,
  libellePeriode,
  libelleSujet,
} from "@/lib/marches";
import type { Marche, ModeleMarche, SujetMarche } from "@/lib/types";

interface EquipeSimple {
  id: string;
  name: string;
}

interface LigneSelection {
  code: string;
  label: string;
  odds: string;
}

interface FormMarche {
  template_code: string;
  name: string;
  family: string;
  period: string;
  subject: SujetMarche;
  subject_team_id: string;
  subject_player: string;
  line: string;
  line2: string;
  bookmaker: string;
  source: string;
  captured_at: string;
  notes: string;
  selections: LigneSelection[];
}

const formVide: FormMarche = {
  template_code: "",
  name: "",
  family: "resultat",
  period: "match",
  subject: "match",
  subject_team_id: "",
  subject_player: "",
  line: "",
  line2: "",
  bookmaker: "1xBet",
  source: "manuel",
  captured_at: "",
  notes: "",
  selections: [
    { code: "1", label: "Domicile", odds: "" },
    { code: "X", label: "Match nul", odds: "" },
    { code: "2", label: "Extérieur", odds: "" },
  ],
};

function formDepuisModele(modele: ModeleMarche): FormMarche {
  return {
    ...formVide,
    template_code: modele.code,
    name: modele.name,
    family: modele.family,
    period: modele.period,
    subject: modele.subject,
    selections:
      modele.selection_templates.length > 0
        ? modele.selection_templates.map((item) => ({ ...item, odds: "" }))
        : [{ code: "", label: "", odds: "" }],
  };
}

function nombreOuNull(valeur: string): number | null {
  if (valeur.trim() === "") return null;
  const nombre = Number(valeur.replace(",", "."));
  return Number.isFinite(nombre) ? nombre : null;
}

function pourcent(valeur: number | null): string {
  if (valeur === null) return "—";
  return `${(valeur * 100).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} %`;
}

function cote(valeur: number | null): string {
  if (valeur === null) return "—";
  return valeur.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function cleCote(marcheId: string, selectionId: string): string {
  return `${marcheId}:${selectionId}`;
}

export function PanneauMarches({
  matchId,
  sportCode,
  equipeDomicile,
  equipeExterieur,
}: {
  matchId: string;
  sportCode: string;
  equipeDomicile: EquipeSimple;
  equipeExterieur: EquipeSimple;
}) {
  const [marches, setMarches] = useState<Marche[]>([]);
  const [modeles, setModeles] = useState<ModeleMarche[]>([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [form, setForm] = useState<FormMarche>(formVide);
  const [filtreModele, setFiltreModele] = useState("");
  const [cotes, setCotes] = useState<Record<string, string>>({});

  const chargerMarches = useCallback(async () => {
    const liste = await apiFetch<Marche[]>(`/v1/matches/${matchId}/markets`);
    setMarches(liste);
  }, [matchId]);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        await chargerMarches();
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      } finally {
        if (actif) setChargement(false);
      }
    })();
    return () => {
      actif = false;
    };
  }, [chargerMarches]);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        const catalogue = await apiFetch<ModeleMarche[]>(
          `/v1/markets/catalog?sport_code=${encodeURIComponent(sportCode)}`,
        );
        if (!actif) return;
        setModeles(catalogue);
        setForm((courant) => {
          if (courant.template_code || courant.name.trim()) return courant;
          const defaut =
            catalogue.find((item) => item.code === `${sportCode}.resultat_1x2`) ?? catalogue[0];
          return defaut ? formDepuisModele(defaut) : courant;
        });
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      }
    })();
    return () => {
      actif = false;
    };
  }, [sportCode]);

  function signalerSucces(message: string) {
    setSucces(message);
    setErreur(null);
    setTimeout(() => setSucces(null), 4000);
  }

  const modeleCourant = useMemo(
    () => modeles.find((item) => item.code === form.template_code) ?? null,
    [modeles, form.template_code],
  );

  const modelesAffiches = useMemo(() => {
    const recherche = filtreModele.trim().toLowerCase();
    if (!recherche) return modeles;
    return modeles.filter(
      (item) =>
        item.name.toLowerCase().includes(recherche) ||
        libelleFamille(item.family).toLowerCase().includes(recherche),
    );
  }, [modeles, filtreModele]);

  const groupes = useMemo(() => {
    const map = new Map<string, ModeleMarche[]>();
    for (const modele of modelesAffiches) {
      const liste = map.get(modele.family) ?? [];
      liste.push(modele);
      map.set(modele.family, liste);
    }
    return [...map.entries()].sort((a, b) => libelleFamille(a[0]).localeCompare(libelleFamille(b[0])));
  }, [modelesAffiches]);

  function choisirModele(code: string) {
    if (!code) {
      setForm({ ...formVide });
      return;
    }
    const modele = modeles.find((item) => item.code === code);
    if (modele) setForm(formDepuisModele(modele));
  }

  function modifierSelection(index: number, champ: "label" | "odds", valeur: string) {
    setForm((courant) => ({
      ...courant,
      selections: courant.selections.map((item, position) =>
        position === index ? { ...item, [champ]: valeur } : item,
      ),
    }));
  }

  function ajouterLigneSelection() {
    setForm((courant) => ({
      ...courant,
      selections: [...courant.selections, { code: "", label: "", odds: "" }],
    }));
  }

  function retirerLigneSelection(index: number) {
    setForm((courant) => ({
      ...courant,
      selections: courant.selections.filter((_, position) => position !== index),
    }));
  }

  async function creerMarche(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    setErreur(null);

    if (form.subject === "team" && !form.subject_team_id) {
      setErreur("Choisissez l'équipe concernée par ce marché.");
      return;
    }
    if (form.subject === "player" && !form.subject_player.trim()) {
      setErreur("Indiquez le nom du joueur concerné par ce marché.");
      return;
    }
    if (!form.template_code && (!form.name.trim() || !form.family.trim())) {
      setErreur("Un marché personnalisé doit avoir un nom et une famille.");
      return;
    }

    const typeLigne = modeleCourant?.line_kind ?? "libre";
    if ((typeLigne === "simple" || typeLigne === "intervalle") && nombreOuNull(form.line) === null) {
      setErreur("Ce marché nécessite une ligne (par exemple 2,5 buts).");
      return;
    }
    if (typeLigne === "double" && (nombreOuNull(form.line) === null || nombreOuNull(form.line2) === null)) {
      setErreur("Ce marché nécessite deux lignes.");
      return;
    }

    const selections = form.selections
      .filter((item) => item.label.trim() !== "")
      .map((item) => ({
        code: item.code || undefined,
        label: item.label.trim(),
        decimal_odds: nombreOuNull(item.odds),
      }));
    if (selections.length === 0) {
      setErreur("Ajoutez au moins une sélection avec un libellé.");
      return;
    }
    if (selections.some((item) => item.decimal_odds !== null && item.decimal_odds <= 1)) {
      setErreur("Chaque cote doit être strictement supérieure à 1.");
      return;
    }

    setEnvoi(true);
    try {
      await apiFetch<Marche>(`/v1/matches/${matchId}/markets`, {
        corps: {
          template_code: form.template_code || null,
          name: form.template_code ? null : form.name.trim(),
          family: form.template_code ? null : form.family.trim(),
          period: form.period,
          subject: form.subject,
          subject_team_id: form.subject === "team" ? form.subject_team_id : null,
          subject_player: form.subject === "player" ? form.subject_player.trim() : null,
          line: nombreOuNull(form.line),
          line2: nombreOuNull(form.line2),
          selections,
          bookmaker: form.bookmaker.trim() || "1xBet",
          source: form.source.trim() || "manuel",
          captured_at: form.captured_at ? new Date(form.captured_at).toISOString() : null,
          notes: form.notes.trim() || null,
        },
      });
      await chargerMarches();
      setForm((courant) => ({
        ...courant,
        selections: courant.selections.map((item) => ({ ...item, odds: "" })),
      }));
      signalerSucces("Marché ajouté. Saisissez une nouvelle cote quand elle évolue.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnvoi(false);
    }
  }

  async function ajouterCote(marcheId: string, selectionId: string) {
    const cle = cleCote(marcheId, selectionId);
    const valeur = nombreOuNull(cotes[cle] ?? "");
    if (valeur === null || valeur <= 1) {
      setErreur("Saisissez une cote décimale strictement supérieure à 1.");
      return;
    }
    setErreur(null);
    try {
      await apiFetch<Marche>(`/v1/markets/${marcheId}/selections/${selectionId}/odds`, {
        corps: { decimal_odds: valeur },
      });
      setCotes((courant) => ({ ...courant, [cle]: "" }));
      await chargerMarches();
      signalerSucces("Nouveau relevé de cote enregistré (l'ancien est conservé).");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function supprimerCote(marcheId: string, selectionId: string, coteId: string) {
    if (!window.confirm("Supprimer définitivement ce relevé de cote erroné ?")) return;
    try {
      await apiFetch<void>(
        `/v1/markets/${marcheId}/selections/${selectionId}/odds/${coteId}`,
        { methode: "DELETE" },
      );
      await chargerMarches();
      signalerSucces("Relevé supprimé.");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function supprimerMarche(marche: Marche) {
    if (
      !window.confirm(
        `Supprimer le marché « ${marche.name} » et tout son historique de cotes ?`,
      )
    ) {
      return;
    }
    try {
      await apiFetch<void>(`/v1/markets/${marche.id}`, { methode: "DELETE" });
      await chargerMarches();
      signalerSucces("Marché supprimé.");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  const typeLigne = modeleCourant?.line_kind ?? "libre";

  return (
    <Panneau
      titre={`Marchés et cotes (${marches.length})`}
      description="Saisie manuelle des cotes 1xBet. Chaque ajout crée un relevé horodaté : une cote n'est jamais écrasée. Les probabilités et la marge sont indicatives, jamais une certitude."
    >
      <div className="flex flex-col gap-4">
        {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
        {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

        <form onSubmit={creerMarche} className="flex flex-col gap-4 rounded-xl border border-bordure bg-fond p-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Champ label="Filtrer le catalogue" aide="Tapez « corners », « joueur », « total »…">
              <Saisie
                value={filtreModele}
                onChange={(e) => setFiltreModele(e.target.value)}
                placeholder="Rechercher un marché"
              />
            </Champ>

            <Champ
              label="Marché du catalogue"
              className="lg:col-span-2"
              aide={`${modeles.length} modèles disponibles pour ce sport. Choisissez « Marché personnalisé » pour toute variante absente.`}
            >
              <Selection value={form.template_code} onChange={(e) => choisirModele(e.target.value)}>
                <option value="">— Marché personnalisé —</option>
                {groupes.map(([famille, liste]) => (
                  <optgroup key={famille} label={libelleFamille(famille)}>
                    {liste.map((modele) => (
                      <option key={modele.code} value={modele.code}>
                        {modele.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </Selection>
            </Champ>
          </div>

          {form.template_code && modeleCourant ? (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-bordure-forte bg-fond-eleve px-3 py-2 text-[11px] text-texte-doux">
              <Badge ton="accent">{libelleFamille(modeleCourant.family)}</Badge>
              <span>{libellePeriode(modeleCourant.period)}</span>
              <span>·</span>
              <span>{libelleSujet(modeleCourant.subject)}</span>
              {modeleCourant.description ? (
                <>
                  <span>·</span>
                  <span>{modeleCourant.description}</span>
                </>
              ) : null}
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Champ label="Nom du marché" className="sm:col-span-2">
                <Saisie
                  required
                  maxLength={160}
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Ex. Cartons par joueur — variante maison"
                />
              </Champ>
              <Champ label="Famille">
                <Saisie
                  required
                  maxLength={80}
                  value={form.family}
                  onChange={(e) => setForm({ ...form, family: e.target.value })}
                  placeholder="corners, cartons, joueur…"
                />
              </Champ>
              <Champ label="Période">
                <Saisie
                  required
                  maxLength={40}
                  value={form.period}
                  onChange={(e) => setForm({ ...form, period: e.target.value })}
                  placeholder="match, mi_temps…"
                />
              </Champ>
              <Champ label="Sujet">
                <Selection
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value as SujetMarche })}
                >
                  <option value="match">Match</option>
                  <option value="team">Équipe</option>
                  <option value="player">Joueur</option>
                </Selection>
              </Champ>
            </div>
          )}

          {form.subject === "team" ? (
            <Champ label="Équipe concernée">
              <Selection
                required
                value={form.subject_team_id}
                onChange={(e) => setForm({ ...form, subject_team_id: e.target.value })}
              >
                <option value="">—</option>
                <option value={equipeDomicile.id}>{equipeDomicile.name}</option>
                <option value={equipeExterieur.id}>{equipeExterieur.name}</option>
              </Selection>
            </Champ>
          ) : null}

          {form.subject === "player" ? (
            <Champ label="Joueur concerné">
              <Saisie
                required
                maxLength={120}
                value={form.subject_player}
                onChange={(e) => setForm({ ...form, subject_player: e.target.value })}
                placeholder="Nom du joueur"
              />
            </Champ>
          ) : null}

          {typeLigne === "simple" || typeLigne === "intervalle" || typeLigne === "libre" ? (
            <Champ
              label={typeLigne === "libre" ? "Ligne (optionnelle)" : "Ligne"}
              aide="Ex. 2,5 buts, +1,5, 9,5 corners."
            >
              <Saisie
                type="number"
                step="0.01"
                value={form.line}
                onChange={(e) => setForm({ ...form, line: e.target.value })}
              />
            </Champ>
          ) : null}

          {typeLigne === "double" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <Champ label="Première ligne">
                <Saisie
                  type="number"
                  step="0.01"
                  value={form.line}
                  onChange={(e) => setForm({ ...form, line: e.target.value })}
                />
              </Champ>
              <Champ label="Seconde ligne">
                <Saisie
                  type="number"
                  step="0.01"
                  value={form.line2}
                  onChange={(e) => setForm({ ...form, line2: e.target.value })}
                />
              </Champ>
            </div>
          ) : null}

          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-xs font-semibold text-texte">Sélections et cotes</h3>
              <Bouton type="button" variante="discret" onClick={ajouterLigneSelection}>
                + Ajouter une sélection
              </Bouton>
            </div>
            <p className="mt-1 text-[11px] text-texte-faible">
              Laissez la cote vide pour créer le marché sans cote initiale. La cote doit être
              strictement supérieure à 1.
            </p>
            <div className="mt-2 flex flex-col gap-2">
              {form.selections.map((item, index) => (
                <div key={`${index}-${item.code}`} className="grid gap-2 sm:grid-cols-[1fr_140px_auto]">
                  <Saisie
                    maxLength={120}
                    value={item.label}
                    onChange={(e) => modifierSelection(index, "label", e.target.value)}
                    placeholder="Libellé (ex. Plus de 2,5)"
                  />
                  <Saisie
                    type="number"
                    step="0.01"
                    min="1.01"
                    value={item.odds}
                    onChange={(e) => modifierSelection(index, "odds", e.target.value)}
                    placeholder="Cote"
                  />
                  <Bouton
                    type="button"
                    variante="discret"
                    onClick={() => retirerLigneSelection(index)}
                    aria-label="Retirer cette sélection"
                  >
                    Retirer
                  </Bouton>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Champ label="Bookmaker">
              <Saisie
                maxLength={80}
                value={form.bookmaker}
                onChange={(e) => setForm({ ...form, bookmaker: e.target.value })}
              />
            </Champ>
            <Champ label="Source">
              <Saisie
                maxLength={40}
                value={form.source}
                onChange={(e) => setForm({ ...form, source: e.target.value })}
              />
            </Champ>
            <Champ label="Date du relevé (optionnel)">
              <Saisie
                type="datetime-local"
                value={form.captured_at}
                onChange={(e) => setForm({ ...form, captured_at: e.target.value })}
              />
            </Champ>
            <Champ label="Note (optionnel)">
              <Saisie
                maxLength={1000}
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Champ>
          </div>

          <div>
            <Bouton type="submit" variante="principal" disabled={envoi}>
              {envoi ? "Ajout…" : "Ajouter le marché"}
            </Bouton>
          </div>
        </form>

        {chargement ? (
          <Chargement libelle="Chargement des marchés…" />
        ) : marches.length === 0 ? (
          <EtatVide>
            Aucun marché saisi. Choisissez un modèle du catalogue ou créez un marché personnalisé.
          </EtatVide>
        ) : (
          <div className="flex flex-col gap-3">
            {marches.map((marche) => {
              const ligne = descriptionMarche(marche);
              const margeNegative =
                marche.overround_percent !== null && marche.overround_percent < 0;
              return (
                <article
                  key={marche.id}
                  className="rounded-xl border border-bordure bg-fond p-4"
                >
                  <header className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-texte">{marche.name}</h3>
                        {marche.is_custom ? <Badge>Personnalisé</Badge> : null}
                        <Badge ton={marche.is_complete && !margeNegative ? "accent" : "alerte"}>
                          {marche.is_complete && marche.overround_percent !== null
                            ? margeNegative
                              ? `Cotes incohérentes (${marche.overround_percent.toLocaleString(
                                  "fr-FR",
                                  { maximumFractionDigits: 2 },
                                )} %)`
                              : `Marge ${marche.overround_percent.toLocaleString("fr-FR", {
                                  maximumFractionDigits: 2,
                                })} %`
                            : "Cotes incomplètes"}
                        </Badge>
                      </div>
                      <p className="mt-1 text-[11px] text-texte-faible">
                        {libelleFamille(marche.family)} · {libellePeriode(marche.period)} ·{" "}
                        {libelleSujet(marche.subject)}
                        {ligne ? ` · ${ligne}` : ""}
                        {marche.latest_captured_at
                          ? ` · dernier relevé ${formatDateHeure(marche.latest_captured_at)}`
                          : ""}
                      </p>
                    </div>
                    <Bouton variante="danger" onClick={() => void supprimerMarche(marche)}>
                      Supprimer
                    </Bouton>
                  </header>

                  {marche.is_complete && marche.implied_probability_total !== null ? (
                    <p className="mt-2 text-[11px] text-texte-doux">
                      Somme des probabilités implicites : {pourcent(marche.implied_probability_total)}
                      {" · "}les cotes équitables retirent la marge du bookmaker.
                      {margeNegative
                        ? " Une somme inférieure à 100 % signale des cotes incomplètes ou incohérentes : vérifiez la saisie."
                        : ""}
                    </p>
                  ) : null}

                  <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {marche.selections.map((selection) => {
                      const cle = cleCote(marche.id, selection.id);
                      return (
                        <div
                          key={selection.id}
                          className="rounded-lg border border-bordure-forte bg-fond-eleve p-3"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-xs font-medium text-texte">
                                {selection.label}
                              </p>
                              <p className="mt-0.5 text-[11px] text-texte-faible">
                                Implicite {pourcent(selection.implied_probability)}
                                {selection.fair_odds !== null
                                  ? ` · équitable ${cote(selection.fair_odds)}`
                                  : ""}
                              </p>
                            </div>
                            <span className="shrink-0 font-mono text-sm text-accent">
                              {cote(selection.latest_odds)}
                            </span>
                          </div>

                          <div className="mt-2 flex gap-2">
                            <Saisie
                              type="number"
                              step="0.01"
                              min="1.01"
                              className="py-1 text-xs"
                              placeholder="Nouvelle cote"
                              value={cotes[cle] ?? ""}
                              onChange={(e) =>
                                setCotes((courant) => ({ ...courant, [cle]: e.target.value }))
                              }
                            />
                            <Bouton
                              variante="secondaire"
                              onClick={() => void ajouterCote(marche.id, selection.id)}
                              className="shrink-0"
                            >
                              Ajouter
                            </Bouton>
                          </div>

                          {selection.history.length > 0 ? (
                            <details className="mt-2 text-[11px] text-texte-faible">
                              <summary className="cursor-pointer select-none">
                                Historique ({selection.odds_count})
                              </summary>
                              <ul className="mt-1 flex flex-col gap-1">
                                {selection.history.slice(0, 10).map((item) => (
                                  <li
                                    key={item.id}
                                    className="flex items-center justify-between gap-2"
                                  >
                                    <span className="min-w-0 truncate">
                                      {formatDateHeure(item.captured_at)} · {item.bookmaker}
                                    </span>
                                    <span className="font-mono text-texte-doux">
                                      {cote(item.decimal_odds)}
                                    </span>
                                    <button
                                      type="button"
                                      className="text-danger hover:underline"
                                      title="Supprimer ce relevé erroné"
                                      onClick={() =>
                                        void supprimerCote(marche.id, selection.id, item.id)
                                      }
                                    >
                                      ×
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            </details>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>

                  {marche.notes ? (
                    <p className="mt-2 text-[11px] text-texte-doux">{marche.notes}</p>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </Panneau>
  );
}
