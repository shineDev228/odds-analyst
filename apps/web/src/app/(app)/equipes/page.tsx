"use client";

import { useCallback, useEffect, useState } from "react";

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
import type { Equipe, Page, Sport } from "@/lib/types";

interface FormEquipe {
  sport_id: string;
  name: string;
  short_name: string;
  country: string;
}

const formVide: FormEquipe = { sport_id: "", name: "", short_name: "", country: "" };

export default function PageEquipes() {
  const [sports, setSports] = useState<Sport[]>([]);
  const [equipes, setEquipes] = useState<Equipe[]>([]);
  const [total, setTotal] = useState(0);
  const [recherche, setRecherche] = useState("");
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [form, setForm] = useState<FormEquipe>(formVide);
  const [envoi, setEnvoi] = useState(false);
  const [formOuvert, setFormOuvert] = useState(false);
  const [editionId, setEditionId] = useState<string | null>(null);
  const [edition, setEdition] = useState(formVide);

  const charger = useCallback(async (terme: string) => {
    const parametres = new URLSearchParams({ page_size: "200" });
    if (terme.trim()) parametres.set("search", terme.trim());
    const page = await apiFetch<Page<Equipe>>(`/v1/teams?${parametres}`);
    setEquipes(page.items);
    setTotal(page.total);
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
          if (actif) await charger(recherche);
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
  }, [recherche, charger]);

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
      await apiFetch<Equipe>("/v1/teams", {
        corps: {
          sport_id: form.sport_id,
          name: form.name.trim(),
          short_name: form.short_name.trim() || null,
          country: form.country.trim() || null,
        },
      });
      setForm({ ...formVide, sport_id: form.sport_id });
      setFormOuvert(false);
      await charger(recherche);
      signalerSucces("Équipe créée.");
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnvoi(false);
    }
  }

  function ouvrirEdition(equipe: Equipe) {
    setEditionId(equipe.id);
    setEdition({
      sport_id: equipe.sport_id,
      name: equipe.name,
      short_name: equipe.short_name ?? "",
      country: equipe.country ?? "",
    });
  }

  async function enregistrerEdition() {
    if (!editionId) return;
    setErreur(null);
    try {
      await apiFetch<Equipe>(`/v1/teams/${editionId}`, {
        methode: "PATCH",
        corps: {
          name: edition.name.trim(),
          short_name: edition.short_name.trim() || null,
          country: edition.country.trim() || null,
        },
      });
      setEditionId(null);
      await charger(recherche);
      signalerSucces("Équipe modifiée.");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  async function supprimer(equipe: Equipe) {
    if (!window.confirm(`Supprimer l'équipe « ${equipe.name} » ?`)) return;
    try {
      await apiFetch<void>(`/v1/teams/${equipe.id}`, { methode: "DELETE" });
      await charger(recherche);
      signalerSucces("Équipe supprimée.");
    } catch (error) {
      setErreur(messageErreur(error));
    }
  }

  const nomSport = (id: string) => sports.find((sport) => sport.id === id)?.name ?? "—";
  const equipeEnEdition = equipes.find((item) => item.id === editionId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <EntetePage
        titre="Équipes"
        description="Le référentiel des équipes utilisées dans vos rencontres."
        action={
          <Bouton
            variante={formOuvert ? "secondaire" : "principal"}
            onClick={() => setFormOuvert((ouvert) => !ouvert)}
            aria-expanded={formOuvert}
            aria-controls="nouvelle-equipe"
          >
            {formOuvert ? "Fermer" : "Ajouter une équipe"}
          </Bouton>
        }
      />

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      {formOuvert ? (
        <Panneau titre="Nouvelle équipe">
          <div id="nouvelle-equipe">
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
                  placeholder="Paris Saint-Germain"
                />
              </Champ>
              <Champ label="Nom court">
                <Saisie
                  maxLength={40}
                  value={form.short_name}
                  onChange={(e) => setForm({ ...form, short_name: e.target.value })}
                  placeholder="PSG"
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
              <div className="flex items-end">
                <Bouton type="submit" variante="principal" disabled={envoi} className="w-full">
                  {envoi ? "Création…" : "Ajouter"}
                </Bouton>
              </div>
            </form>
          </div>
        </Panneau>
      ) : null}

      {equipeEnEdition ? (
        <Panneau titre={`Modifier « ${equipeEnEdition.name} »`}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Champ label="Nom">
              <Saisie
                value={edition.name}
                onChange={(e) => setEdition({ ...edition, name: e.target.value })}
              />
            </Champ>
            <Champ label="Nom court">
              <Saisie
                value={edition.short_name}
                onChange={(e) => setEdition({ ...edition, short_name: e.target.value })}
              />
            </Champ>
            <Champ label="Pays">
              <Saisie
                value={edition.country}
                onChange={(e) => setEdition({ ...edition, country: e.target.value })}
              />
            </Champ>
            <div className="flex items-end gap-2">
              <Bouton variante="principal" onClick={() => void enregistrerEdition()}>
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
          {total} équipe{total > 1 ? "s" : ""}
        </p>
        <Saisie
          placeholder="Rechercher…"
          value={recherche}
          onChange={(e) => setRecherche(e.target.value)}
          className="sm:w-56"
          aria-label="Rechercher une équipe"
        />
      </div>

      {chargement ? (
        <Chargement />
      ) : equipes.length === 0 ? (
        <EtatVide>Aucune équipe enregistrée.</EtatVide>
      ) : (
        <Tableau minWidth="680px">
          <thead>
            <tr className="border-b border-bordure-forte text-[11px] text-texte-faible">
              <th className="py-2 pr-3 font-medium">Équipe</th>
              <th className="py-2 pr-3 font-medium">Sport</th>
              <th className="py-2 pr-3 font-medium">Pays</th>
              <th className="py-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {equipes.map((equipe) => (
              <tr key={equipe.id} className="border-b border-bordure/70 hover:bg-fond-panneau">
                <td className="py-2.5 pr-3">
                  <p className="text-sm text-texte">
                    {equipe.name}
                    {equipe.short_name ? (
                      <span className="ml-2 font-mono text-[11px] text-texte-faible">
                        {equipe.short_name}
                      </span>
                    ) : null}
                  </p>
                </td>
                <td className="py-2.5 pr-3 text-xs text-texte-doux">
                  {nomSport(equipe.sport_id)}
                </td>
                <td className="py-2.5 pr-3 text-xs text-texte-doux">
                  {equipe.country ?? "—"}
                </td>
                <td className="py-2.5">
                  <div className="flex flex-wrap justify-end gap-1">
                    <Bouton
                      variante="discret"
                      className="h-8 px-2 text-xs"
                      onClick={() => ouvrirEdition(equipe)}
                    >
                      Modifier
                    </Bouton>
                    <Bouton
                      variante="discret"
                      className="h-8 px-2 text-xs text-texte-faible hover:text-danger"
                      onClick={() => void supprimer(equipe)}
                    >
                      Supprimer
                    </Bouton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Tableau>
      )}
    </div>
  );
}
