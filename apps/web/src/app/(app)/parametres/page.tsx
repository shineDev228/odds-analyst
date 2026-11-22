"use client";

import { useEffect, useState } from "react";

import {
  Alerte,
  Bouton,
  Champ,
  Chargement,
  EntetePage,
  Panneau,
  Saisie,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import { marchesDisponibles } from "@/lib/marches";
import type { Preferences } from "@/lib/types";

export default function PageParametres() {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [reference, setReference] = useState<Preferences | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [enregistrement, setEnregistrement] = useState(false);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        const donnees = await apiFetch<Preferences>("/v1/settings");
        if (actif) {
          setPreferences(donnees);
          setReference(donnees);
        }
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      }
    })();
    return () => {
      actif = false;
    };
  }, []);

  async function enregistrer(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    if (!preferences) return;
    setErreur(null);
    setSucces(null);
    setEnregistrement(true);
    try {
      const donnees = await apiFetch<Preferences>("/v1/settings", {
        methode: "PUT",
        corps: preferences,
      });
      setPreferences(donnees);
      setReference(donnees);
      setSucces("Préférences enregistrées.");
      setTimeout(() => setSucces(null), 4000);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnregistrement(false);
    }
  }

  function basculerMarche(code: string) {
    if (!preferences) return;
    const presents = preferences.marches_autorises.includes(code);
    setPreferences({
      ...preferences,
      marches_autorises: presents
        ? preferences.marches_autorises.filter((item) => item !== code)
        : [...preferences.marches_autorises, code],
    });
  }

  if (!preferences) {
    return erreur ? <Alerte ton="erreur">{erreur}</Alerte> : <Chargement />;
  }

  const modifie =
    reference !== null && JSON.stringify(preferences) !== JSON.stringify(reference);

  return (
    <div className="flex flex-col gap-6">
      <EntetePage
        titre="Paramètres"
        description="Ces valeurs orientent le moteur statistique et le générateur de combinaisons."
      />

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      <form onSubmit={enregistrer} className="flex flex-col gap-6">
        <Panneau
          titre="Modèle et combinaisons"
          description="Fourchette de cote visée, nombre de sélections et fenêtre d'analyse du moteur."
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Champ label="Cote minimale">
              <Saisie
                type="number"
                min={1}
                max={10000}
                step="0.1"
                required
                value={preferences.cote_min}
                onChange={(e) =>
                  setPreferences({ ...preferences, cote_min: Number(e.target.value) })
                }
              />
            </Champ>
            <Champ label="Cote maximale">
              <Saisie
                type="number"
                min={1}
                max={10000}
                step="0.1"
                required
                value={preferences.cote_max}
                onChange={(e) =>
                  setPreferences({ ...preferences, cote_max: Number(e.target.value) })
                }
              />
            </Champ>
            <Champ label="Sélections par défaut" aide="Entre 2 et 15">
              <Saisie
                type="number"
                min={2}
                max={15}
                required
                value={preferences.nb_selections_defaut}
                onChange={(e) =>
                  setPreferences({
                    ...preferences,
                    nb_selections_defaut: Number(e.target.value),
                  })
                }
              />
            </Champ>
            <Champ label="Matchs d'historique" aide="Fenêtre d'analyse par équipe">
              <Saisie
                type="number"
                min={5}
                max={100}
                required
                value={preferences.nb_matchs_historique}
                onChange={(e) =>
                  setPreferences({
                    ...preferences,
                    nb_matchs_historique: Number(e.target.value),
                  })
                }
              />
            </Champ>
            <Champ label="Demi-vie (jours)" aide="Entre 30 et 730 jours">
              <Saisie
                type="number"
                min={30}
                max={730}
                required
                value={preferences.demi_vie_jours}
                onChange={(e) =>
                  setPreferences({ ...preferences, demi_vie_jours: Number(e.target.value) })
                }
              />
            </Champ>
          </div>

          <div className="mt-5 border-t border-bordure pt-4">
            <p className="text-xs font-medium text-texte-doux">Marchés autorisés</p>
            <p className="mt-1 text-[11px] text-texte-faible">
              Seuls ces marchés seront proposés dans les combinaisons.
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {marchesDisponibles.map((marche) => (
                <label
                  key={marche.code}
                  className="flex cursor-pointer items-center gap-3 rounded-md border border-bordure px-3 py-2 text-xs text-texte-doux transition hover:border-accent/40"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-accent"
                    checked={preferences.marches_autorises.includes(marche.code)}
                    onChange={() => basculerMarche(marche.code)}
                  />
                  {marche.libelle}
                </label>
              ))}
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-bordure pt-4">
            <p className="text-[11px] text-texte-faible">
              {modifie ? "Modifications non enregistrées." : "Aucune modification en attente."}
            </p>
            <Bouton
              type="submit"
              variante="principal"
              disabled={enregistrement || !modifie}
            >
              {enregistrement ? "Enregistrement…" : "Enregistrer les préférences"}
            </Bouton>
          </div>
        </Panneau>
      </form>

      <details className="border-t border-bordure pt-5">
        <summary className="cursor-pointer text-xs font-medium text-texte-doux">
          Données et confidentialité
        </summary>
        <ul className="mt-3 flex flex-col gap-2 text-xs leading-relaxed text-texte-doux">
          <li>Toutes les données sont stockées localement, sur votre machine.</li>
          <li>Aucun identifiant de bookmaker n&apos;est demandé ni conservé.</li>
          <li>Aucun scraping non autorisé n&apos;est effectué.</li>
          <li>Aucun pari n&apos;est placé automatiquement.</li>
        </ul>
      </details>
    </div>
  );
}
