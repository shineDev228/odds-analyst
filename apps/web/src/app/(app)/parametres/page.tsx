"use client";

import { useEffect, useState } from "react";

import {
  Alerte,
  Bouton,
  Champ,
  Chargement,
  Panneau,
  Saisie,
} from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import type { Preferences } from "@/lib/types";

const marchesDisponibles = [
  { code: "1X2", libelle: "1X2 (résultat du match)" },
  { code: "DOUBLE_CHANCE", libelle: "Double chance" },
  { code: "PLUS_MOINS", libelle: "Plus / moins de buts" },
];

export default function PageParametres() {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [enregistrement, setEnregistrement] = useState(false);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        const donnees = await apiFetch<Preferences>("/v1/settings");
        if (actif) setPreferences(donnees);
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

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Paramètres</h1>
        <p className="mt-1 text-xs text-texte-doux">
          Ces valeurs orientent le moteur statistique et le générateur de combinaisons.
        </p>
      </header>

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      <form onSubmit={enregistrer} className="flex flex-col gap-6">
        <Panneau
          titre="Combinaisons de cotes"
          description="Fourchette de cote totale visée et nombre de sélections par défaut."
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
          </div>
        </Panneau>

        <Panneau
          titre="Moteur statistique"
          description="Demi-vie de pondération : plus la valeur est faible, plus les matchs récents comptent."
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
        </Panneau>

        <Panneau
          titre="Marchés autorisés"
          description="Seuls ces marchés seront proposés dans les combinaisons."
        >
          <div className="flex flex-col gap-2">
            {marchesDisponibles.map((marche) => (
              <label
                key={marche.code}
                className="flex cursor-pointer items-center gap-3 rounded-lg border border-bordure px-3 py-2 text-xs text-texte-doux transition hover:border-accent/40"
              >
                <input
                  type="checkbox"
                  className="size-4 accent-cyan-400"
                  checked={preferences.marches_autorises.includes(marche.code)}
                  onChange={() => basculerMarche(marche.code)}
                />
                {marche.libelle}
              </label>
            ))}
          </div>
        </Panneau>

        <div>
          <Bouton type="submit" variante="principal" disabled={enregistrement}>
            {enregistrement ? "Enregistrement…" : "Enregistrer les préférences"}
          </Bouton>
        </div>
      </form>

      <Panneau titre="Données et confidentialité">
        <ul className="flex flex-col gap-2 text-xs leading-relaxed text-texte-doux">
          <li>• Toutes les données sont stockées localement, sur votre machine.</li>
          <li>• Aucun identifiant de bookmaker n&apos;est demandé ni conservé.</li>
          <li>• Aucun scraping non autorisé n&apos;est effectué.</li>
          <li>• Aucun pari n&apos;est placé automatiquement.</li>
        </ul>
      </Panneau>
    </div>
  );
}
