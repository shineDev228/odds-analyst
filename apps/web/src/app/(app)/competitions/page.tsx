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
  Saisie,
  Selection,
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

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Compétitions</h1>
        <p className="mt-1 text-xs text-texte-doux">
          Organisez vos compétitions et leurs saisons. Les équipes et rencontres s&apos;y rattachent.
        </p>
      </header>

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      <Panneau titre="Nouvelle compétition">
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
            <Bouton type="submit" variante="principal" disabled={envoi} className="w-full py-2">
              {envoi ? "Création…" : "Ajouter"}
            </Bouton>
          </div>
        </form>
      </Panneau>

      <Panneau
        titre={`Compétitions (${competitions.length})`}
        action={
          <Saisie
            placeholder="Rechercher…"
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
            className="w-48"
            aria-label="Rechercher une compétition"
          />
        }
      >
        {chargement ? (
          <Chargement />
        ) : competitions.length === 0 ? (
          <EtatVide>Aucune compétition enregistrée.</EtatVide>
        ) : (
          <ul className="flex flex-col gap-2">
            {competitions.map((competition) => (
              <li
                key={competition.id}
                className="rounded-xl border border-bordure bg-fond p-3"
              >
                {editionId === competition.id ? (
                  <div className="grid gap-3 sm:grid-cols-4">
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
                        onClick={() => void enregistrerEdition(competition)}
                      >
                        Enregistrer
                      </Bouton>
                      <Bouton variante="discret" onClick={() => setEditionId(null)}>
                        Annuler
                      </Bouton>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium text-texte">{competition.name}</p>
                        {competition.is_active ? (
                          <Badge ton="succes">Active</Badge>
                        ) : (
                          <Badge ton="neutre">Inactive</Badge>
                        )}
                      </div>
                      <p className="mt-0.5 text-[11px] text-texte-faible">
                        {nomSport(competition.sport_id)}
                        {competition.country ? ` · ${competition.country}` : ""}
                        {competition.tier ? ` · niveau ${competition.tier}` : ""}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <Bouton onClick={() => void basculerSaisons(competition)}>
                        Saisons
                      </Bouton>
                      <Bouton onClick={() => ouvrirEdition(competition)}>Modifier</Bouton>
                      <Bouton variante="discret" onClick={() => void basculerActive(competition)}>
                        {competition.is_active ? "Désactiver" : "Activer"}
                      </Bouton>
                      <Bouton variante="danger" onClick={() => void supprimer(competition)}>
                        Supprimer
                      </Bouton>
                    </div>
                  </div>
                )}

                {ouverteId === competition.id ? (
                  <div className="mt-3 border-t border-bordure pt-3">
                    {(saisons[competition.id] ?? []).length === 0 ? (
                      <p className="text-[11px] text-texte-faible">
                        Aucune saison : ajoutez-en une pour pouvoir créer des rencontres.
                      </p>
                    ) : (
                      <ul className="flex flex-col gap-1.5">
                        {(saisons[competition.id] ?? []).map((saison) => (
                          <li
                            key={saison.id}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-bordure/70 px-3 py-2"
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
                              variante="danger"
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
                          onChange={(e) => setFormSaison({ ...formSaison, label: e.target.value })}
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
                          className="w-full py-2"
                          disabled={formSaison.label.trim().length < 2}
                          onClick={() => void ajouterSaison(competition.id)}
                        >
                          Ajouter la saison
                        </Bouton>
                      </div>
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panneau>
    </div>
  );
}
