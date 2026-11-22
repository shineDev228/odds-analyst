"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

import {
  Alerte,
  Bouton,
  Champ,
  Chargement,
  EntetePage,
  EtatVide,
  Panneau,
  Saisie,
  Selection,
  Tableau,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Competition, Page, Saison, Sport } from "@/lib/types";

interface FormCompetition {
  sport_id: string;
  name: string;
  country: string;
  tier: string;
}

const formVide: FormCompetition = { sport_id: "", name: "", country: "", tier: "" };

export default function PageCompetitions() {
  const [sports, setSports] = useState<Sport[]>([]);
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [recherche, setRecherche] = useState("");
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [form, setForm] = useState<FormCompetition>(formVide);
  const [envoi, setEnvoi] = useState(false);
  const [formOuvert, setFormOuvert] = useState(false);

  const [editionId, setEditionId] = useState<string | null>(null);
  const [edition, setEdition] = useState<FormCompetition>(formVide);

  const [ouverteId, setOuverteId] = useState<string | null>(null);
  const [saisons, setSaisons] = useState<Record<string, Saison[]>>({});
  const [formSaison, setFormSaison] = useState({ label: "", start_date: "", end_date: "" });

  const chargerCompetitions = useCallback(async (terme: string) => {
    const parametres = new URLSearchParams({ page_size: "200" });
    if (terme.trim()) parametres.set("search", terme.trim());
    const page = await apiFetch<Page<Competition>>(`/v1/competitions?${parametres}`);
    setCompetitions(page.items);
  }, []);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        const liste = await apiFetch<Sport[]>("/v1/sports");
        if (!actif) return;
        setSports(liste);
        setForm((courant) =>
          courant.sport_id || liste.length === 0 ? courant : { ...courant, sport_id: liste[0].id },
        );
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
    const minuteur = setTimeout(() => {
      void (async () => {
        try {
          if (actif) await chargerCompetitions(recherche);
        } catch (error) {
          if (actif) setErreur(messageErreur(error));
        } finally {
          if (actif) setChargement(false);
        }
      })();
    }, 250);
    return () => {
      actif = false;
      clearTimeout(minuteur);
    };
  }, [recherche, chargerCompetitions]);

  function signalerSucces(message: string) {
    setSucces(message);
    setErreur(null);
    setTimeout(() => setSucces(null), 4000);
  }

  async function creer(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    setErreur(null);
    if (!form.sport_id) {
      setErreur("Sélectionnez un sport.");
      return;
    }
    setEnvoi(true);
    try {
      await apiFetch<Competition>("/v1/competitions", {
        corps: {
          sport_id: form.sport_id,
          name: form.name.trim(),
          country: form.country.trim() || null,
          tier: form.tier ? Number(form.tier) : null,
        },
      });
      setForm({ ...formVide, sport_id: form.sport_id });
      setFormOuvert(false);
      await chargerCompetitions(recherche);
      signalerSucces("Compétition créée.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnvoi(false);
    }
  }

  function ouvrirEdition(competition: Competition) {
    setEditionId(competition.id);
    setEdition({
      sport_id: competition.sport_id,
      name: competition.name,
      country: competition.country ?? "",
      tier: competition.tier ? String(competition.tier) : "",
    });
  }

  async function enregistrerEdition(competition: Competition) {
    setErreur(null);
    try {
      await apiFetch<Competition>(`/v1/competitions/${competition.id}`, {
        methode: "PATCH",
        corps: {
          name: edition.name.trim(),
          country: edition.country.trim() || null,
          tier: edition.tier ? Number(edition.tier) : null,
          is_active: competition.is_active,
        },
      });
      setEditionId(null);
      await chargerCompetitions(recherche);
      signalerSucces("Compétition modifiée.");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function basculerActive(competition: Competition) {
    try {
      await apiFetch(`/v1/competitions/${competition.id}`, {
        methode: "PATCH",
        corps: { is_active: !competition.is_active },
      });
      await chargerCompetitions(recherche);
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function supprimer(competition: Competition) {
    if (!window.confirm(`Supprimer la compétition « ${competition.name} » et ses saisons ?`)) {
      return;
    }
    try {
      await apiFetch<void>(`/v1/competitions/${competition.id}`, { methode: "DELETE" });
      if (ouverteId === competition.id) setOuverteId(null);
      await chargerCompetitions(recherche);
      signalerSucces("Compétition supprimée.");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function basculerSaisons(competition: Competition) {
    if (ouverteId === competition.id) {
      setOuverteId(null);
      return;
    }
    setOuverteId(competition.id);
    setFormSaison({ label: "", start_date: "", end_date: "" });
    try {
      const page = await apiFetch<Page<Saison>>(
        `/v1/seasons?competition_id=${competition.id}&page_size=200`,
      );
      setSaisons((courant) => ({ ...courant, [competition.id]: page.items }));
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function rechargerSaisons(competitionId: string) {
    const page = await apiFetch<Page<Saison>>(
      `/v1/seasons?competition_id=${competitionId}&page_size=200`,
    );
    setSaisons((courant) => ({ ...courant, [competitionId]: page.items }));
  }

  async function ajouterSaison(competitionId: string) {
    setErreur(null);
    try {
      await apiFetch<Saison>("/v1/seasons", {
        corps: {
          competition_id: competitionId,
          label: formSaison.label.trim(),
          start_date: formSaison.start_date || null,
          end_date: formSaison.end_date || null,
          is_current: true,
        },
      });
      setFormSaison({ label: "", start_date: "", end_date: "" });
      await rechargerSaisons(competitionId);
      signalerSucces("Saison ajoutée.");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function supprimerSaison(competitionId: string, saison: Saison) {
    if (!window.confirm(`Supprimer la saison « ${saison.label} » ?`)) return;
    try {
      await apiFetch<void>(`/v1/seasons/${saison.id}`, { methode: "DELETE" });
      await rechargerSaisons(competitionId);
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  const nomSport = (id: string) => sports.find((sport) => sport.id === id)?.name ?? "—";
  const competitionEnEdition = competitions.find((item) => item.id === editionId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <EntetePage
        titre="Compétitions"
        description="Organisez les compétitions et leurs saisons. Les équipes et rencontres s'y rattachent."
        action={
          <Bouton
            variante={formOuvert ? "secondaire" : "principal"}
            onClick={() => setFormOuvert((ouvert) => !ouvert)}
            aria-expanded={formOuvert}
            aria-controls="nouvelle-competition"
          >
            {formOuvert ? "Fermer" : "Ajouter une compétition"}
          </Bouton>
        }
      />

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      {formOuvert ? (
        <Panneau
          titre="Nouvelle compétition"
          className="scroll-mt-4"
        >
          <div id="nouvelle-competition">
            <form onSubmit={creer} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <Champ label="Sport">
                <Selection
                  required
                  value={form.sport_id}
                  onChange={(e) => setForm({ ...form, sport_id: e.target.value })}
                >
                  <option value="">—</option>
                  {sports.map((sport) => (
                    <option key={sport.id} value={sport.id}>
                      {sport.name}
                    </option>
                  ))}
                </Selection>
              </Champ>

              <Champ label="Nom">
                <Saisie
                  required
                  minLength={2}
                  maxLength={120}
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Ligue 1"
                />
              </Champ>

              <Champ label="Pays">
                <Saisie
                  maxLength={80}
                  value={form.country}
                  onChange={(e) => setForm({ ...form, country: e.target.value })}
                  placeholder="France"
                />
              </Champ>

              <Champ label="Niveau" aide="1 = élite">
                <Saisie
                  type="number"
                  min={1}
                  max={10}
                  value={form.tier}
                  onChange={(e) => setForm({ ...form, tier: e.target.value })}
                />
              </Champ>

              <div className="flex items-end">
                <Bouton type="submit" variante="principal" disabled={envoi} className="w-full">
                  {envoi ? "Création…" : "Ajouter"}
                </Bouton>
              </div>
            </form>
          </div>
        </Panneau>
      ) : null}

      {competitionEnEdition ? (
        <Panneau titre={`Modifier « ${competitionEnEdition.name} »`}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Champ label="Nom">
              <Saisie
                value={edition.name}
                onChange={(e) => setEdition({ ...edition, name: e.target.value })}
              />
            </Champ>
            <Champ label="Pays">
              <Saisie
                value={edition.country}
                onChange={(e) => setEdition({ ...edition, country: e.target.value })}
              />
            </Champ>
            <Champ label="Niveau">
              <Saisie
                type="number"
                min={1}
                max={10}
                value={edition.tier}
                onChange={(e) => setEdition({ ...edition, tier: e.target.value })}
              />
            </Champ>
            <div className="flex items-end gap-2">
              <Bouton
                variante="principal"
                onClick={() => void enregistrerEdition(competitionEnEdition)}
              >
                Enregistrer
              </Bouton>
              <Bouton variante="discret" onClick={() => setEditionId(null)}>
                Annuler
              </Bouton>
            </div>
          </div>
        </Panneau>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 border-y border-bordure py-3">
        <p className="text-xs text-texte-faible">
          {competitions.length} compétition{competitions.length > 1 ? "s" : ""}
        </p>
        <Saisie
          placeholder="Rechercher…"
          value={recherche}
          onChange={(e) => setRecherche(e.target.value)}
          className="sm:w-56"
          aria-label="Rechercher une compétition"
        />
      </div>

      {chargement ? (
        <Chargement />
      ) : competitions.length === 0 ? (
        <EtatVide>Aucune compétition enregistrée.</EtatVide>
      ) : (
        <Tableau minWidth="720px">
          <thead>
            <tr className="border-b border-bordure-forte text-[11px] text-texte-faible">
              <th className="py-2 pr-3 font-medium">Compétition</th>
              <th className="py-2 pr-3 font-medium">Sport</th>
              <th className="py-2 pr-3 font-medium">Pays</th>
              <th className="py-2 pr-3 text-right font-medium">Niveau</th>
              <th className="py-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {competitions.map((competition) => (
              <Fragment key={competition.id}>
                <tr className="border-b border-bordure/70 hover:bg-fond-panneau">
                  <td className="py-2.5 pr-3">
                    <p className="text-sm text-texte">{competition.name}</p>
                    <span className="mt-0.5 inline-flex items-center gap-1.5 text-[11px] text-texte-faible">
                      <span
                        aria-hidden
                        className={`size-1.5 rounded-full ${
                          competition.is_active ? "bg-succes" : "bg-texte-faible"
                        }`}
                      />
                      {competition.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="py-2.5 pr-3 text-xs text-texte-doux">
                    {nomSport(competition.sport_id)}
                  </td>
                  <td className="py-2.5 pr-3 text-xs text-texte-doux">
                    {competition.country ?? "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-right font-mono text-xs text-texte-doux">
                    {competition.tier ?? "—"}
                  </td>
                  <td className="py-2.5">
                    <div className="flex flex-wrap justify-end gap-1">
                      <Bouton
                        variante="discret"
                        className="h-8 px-2 text-xs"
                        onClick={() => void basculerSaisons(competition)}
                      >
                        Saisons
                      </Bouton>
                      <Bouton
                        variante="discret"
                        className="h-8 px-2 text-xs"
                        onClick={() => ouvrirEdition(competition)}
                      >
                        Modifier
                      </Bouton>
                      <Bouton
                        variante="discret"
                        className="h-8 px-2 text-xs"
                        onClick={() => void basculerActive(competition)}
                      >
                        {competition.is_active ? "Désactiver" : "Activer"}
                      </Bouton>
                      <Bouton
                        variante="discret"
                        className="h-8 px-2 text-xs text-texte-faible hover:text-danger"
                        onClick={() => void supprimer(competition)}
                      >
                        Supprimer
                      </Bouton>
                    </div>
                  </td>
                </tr>

                {ouverteId === competition.id ? (
                  <tr className="border-b border-bordure/70 bg-fond-panneau">
                    <td colSpan={5} className="px-4 py-3">
                      {(saisons[competition.id] ?? []).length === 0 ? (
                        <p className="text-xs text-texte-faible">
                          Aucune saison : ajoutez-en une pour pouvoir créer des rencontres.
                        </p>
                      ) : (
                        <ul className="flex flex-col gap-1">
                          {(saisons[competition.id] ?? []).map((saison) => (
                            <li
                              key={saison.id}
                              className="flex flex-wrap items-center justify-between gap-2 border-b border-bordure/60 py-1.5 last:border-0"
                            >
                              <div>
                                <p className="text-xs text-texte">{saison.label}</p>
                                <p className="text-[11px] text-texte-faible">
                                  {saison.start_date ? formatDate(saison.start_date) : "début ?"}
                                  {" → "}
                                  {saison.end_date ? formatDate(saison.end_date) : "fin ?"}
                                </p>
                              </div>
                              <Bouton
                                variante="discret"
                                className="h-8 px-2 text-xs"
                                onClick={() => void supprimerSaison(competition.id, saison)}
                              >
                                Supprimer
                              </Bouton>
                            </li>
                          ))}
                        </ul>
                      )}

                      <div className="mt-3 grid gap-2 sm:grid-cols-4">
                        <Champ label="Libellé">
                          <Saisie
                            value={formSaison.label}
                            onChange={(e) =>
                              setFormSaison({ ...formSaison, label: e.target.value })
                            }
                            placeholder="2026-2027"
                          />
                        </Champ>
                        <Champ label="Début">
                          <Saisie
                            type="date"
                            value={formSaison.start_date}
                            onChange={(e) =>
                              setFormSaison({ ...formSaison, start_date: e.target.value })
                            }
                          />
                        </Champ>
                        <Champ label="Fin">
                          <Saisie
                            type="date"
                            value={formSaison.end_date}
                            onChange={(e) =>
                              setFormSaison({ ...formSaison, end_date: e.target.value })
                            }
                          />
                        </Champ>
                        <div className="flex items-end">
                          <Bouton
                            variante="principal"
                            className="w-full"
                            disabled={formSaison.label.trim().length < 2}
                            onClick={() => void ajouterSaison(competition.id)}
                          >
                            Ajouter la saison
                          </Bouton>
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </Tableau>
      )}
    </div>
  );
}
