"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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
  Combinaison,
  CombinaisonEnregistree,
  Preferences,
  ReponseCombinaisons,
} from "@/lib/types";

const marchesDisponibles = [
  { code: "1X2", libelle: "1X2 (résultat du match)" },
  { code: "DOUBLE_CHANCE", libelle: "Double chance" },
  { code: "PLUS_MOINS", libelle: "Plus / moins de buts" },
  { code: "BTTS", libelle: "Les deux équipes marquent" },
];

interface FormCombinaison {
  nombre_selections: number;
  cote_min: number;
  cote_max: number;
  marches_autorises: string[];
  limite: number;
}

function pourcent(valeur: number): string {
  const points = valeur * 100;
  if (points > 0 && points < 0.01) return "< 0,01 %";
  return `${points.toLocaleString("fr-FR", {
    minimumFractionDigits: points > 0 && points < 1 ? 2 : 0,
    maximumFractionDigits: points > 0 && points < 1 ? 2 : 1,
  })} %`;
}

function fourchette(item: { low: number; high: number }): string {
  return `${pourcent(item.low)} – ${pourcent(item.high)}`;
}

function cote(valeur: number): string {
  return valeur.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function esperance(valeur: number): string {
  return `${(valeur * 100).toLocaleString("fr-FR", {
    signDisplay: "exceptZero",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} %`;
}

function tonEsperance(valeur: number): "succes" | "danger" | "neutre" {
  if (valeur > 0) return "succes";
  if (valeur < 0) return "danger";
  return "neutre";
}

function cleCombinaison(combinaison: Combinaison): string {
  return combinaison.selections
    .map((item) => `${item.selection_id}:${item.decimal_odds}`)
    .join("|");
}

function CarteCombinaison({
  combinaison,
  rang,
  onEnregistrer,
  enregistrement,
  dejaEnregistree,
}: {
  combinaison: Combinaison;
  rang: number;
  onEnregistrer: () => void;
  enregistrement: boolean;
  dejaEnregistree: boolean;
}) {
  return (
    <article className="rounded-xl border border-bordure bg-fond p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge ton="accent">Combinaison {rang}</Badge>
            <span className="text-[11px] text-texte-faible">
              {combinaison.selections.length} sélections
            </span>
          </div>
          <p className="mt-2 text-xs text-texte-doux">
            Cote totale{" "}
            <span className="font-mono text-lg text-texte">
              {cote(combinaison.total_odds)}
            </span>
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Bouton
              type="button"
              variante="secondaire"
              onClick={onEnregistrer}
              disabled={enregistrement || dejaEnregistree}
            >
              {dejaEnregistree
                ? "Enregistrée"
                : enregistrement
                  ? "Enregistrement…"
                  : "Enregistrer dans l'historique"}
            </Bouton>
            {dejaEnregistree ? (
              <Link
                href="/historique"
                className="text-[11px] font-medium text-accent hover:underline"
              >
                Voir l&apos;historique
              </Link>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-right text-[11px]">
          <span className="text-texte-faible">Probabilité estimée</span>
          <span className="font-mono text-texte">
            {pourcent(combinaison.probability)}
          </span>
          <span className="text-texte-faible">Fourchette 80 %</span>
          <span className="font-mono text-texte-doux">
            {fourchette(combinaison)}
          </span>
          <span className="text-texte-faible">Espérance estimée</span>
          <span>
            <Badge ton={tonEsperance(combinaison.expected_value)}>
              {esperance(combinaison.expected_value)}
            </Badge>
          </span>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-[11px]">
          <thead>
            <tr className="border-b border-bordure text-texte-faible">
              <th className="pb-2 pr-3 font-medium">Rencontre</th>
              <th className="pb-2 pr-3 font-medium">Marché</th>
              <th className="pb-2 pr-3 font-medium">Choix</th>
              <th className="pb-2 pr-3 text-right font-medium">Cote</th>
              <th className="pb-2 text-right font-medium">Probabilité estimée</th>
            </tr>
          </thead>
          <tbody>
            {combinaison.selections.map((selection) => (
              <tr
                key={`${selection.match_id}-${selection.market_name}-${selection.selection_label}`}
                className="border-b border-bordure/60 last:border-0"
              >
                <td className="py-2 pr-3">
                  <p className="text-texte">{selection.match_label}</p>
                  <p className="text-texte-faible">
                    {selection.competition_name} ·{" "}
                    {formatDateHeure(selection.kickoff_at)}
                  </p>
                </td>
                <td className="py-2 pr-3 text-texte-doux">{selection.market_name}</td>
                <td className="py-2 pr-3 text-texte">{selection.selection_label}</td>
                <td className="py-2 pr-3 text-right font-mono text-texte">
                  {cote(selection.decimal_odds)}
                </td>
                <td className="py-2 text-right">
                  <span className="font-mono text-texte">
                    {pourcent(selection.probability)}
                  </span>
                  <span className="ml-1 text-texte-faible">
                    {" "}
                    ({fourchette(selection)})
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

export default function PageCombinaisons() {
  const [form, setForm] = useState<FormCombinaison | null>(null);
  const [reponse, setReponse] = useState<ReponseCombinaisons | null>(null);
  const [chargement, setChargement] = useState(true);
  const [calcul, setCalcul] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [enregistrement, setEnregistrement] = useState<string | null>(null);
  const [enregistrees, setEnregistrees] = useState<Set<string>>(new Set());

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        const preferences = await apiFetch<Preferences>("/v1/settings");
        if (!actif) return;
        setForm({
          nombre_selections: preferences.nb_selections_defaut,
          cote_min: preferences.cote_min,
          cote_max: preferences.cote_max,
          marches_autorises: preferences.marches_autorises,
          limite: 10,
        });
      } catch (error) {
        if (actif) setErreur(messageErreur(error));
      } finally {
        if (actif) setChargement(false);
      }
    })();
    return () => {
      actif = false;
    };
  }, []);

  function basculerMarche(code: string) {
    if (!form) return;
    const presents = form.marches_autorises.includes(code);
    setForm({
      ...form,
      marches_autorises: presents
        ? form.marches_autorises.filter((item) => item !== code)
        : [...form.marches_autorises, code],
    });
  }

  async function generer(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    if (!form) return;
    if (form.marches_autorises.length === 0) {
      setErreur("Sélectionnez au moins un marché.");
      setReponse(null);
      return;
    }
    setErreur(null);
    setSucces(null);
    setReponse(null);
    setCalcul(true);
    try {
      const donnees = await apiFetch<ReponseCombinaisons>(
        "/v1/combinations/generate",
        { methode: "POST", corps: form },
      );
      setReponse(donnees);
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setCalcul(false);
    }
  }

  async function enregistrer(combinaison: Combinaison) {
    if (!reponse || enregistrement) return;
    const cle = cleCombinaison(combinaison);
    if (enregistrees.has(cle)) return;

    setEnregistrement(cle);
    setErreur(null);
    setSucces(null);
    try {
      const sauvee = await apiFetch<CombinaisonEnregistree>("/v1/combinations", {
        methode: "POST",
        corps: {
          selections: combinaison.selections.map((item) => ({
            match_id: item.match_id,
            selection_id: item.selection_id,
            decimal_odds: item.decimal_odds,
          })),
          parametres: reponse.parametres,
          note: null,
        },
      });
      setEnregistrees((courant) => new Set(courant).add(cle));
      setSucces(
        `Combinaison enregistrée avec la cote ${cote(sauvee.total_odds)}. ` +
          "Retrouvez-la dans l'historique pour suivre son règlement.",
      );
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnregistrement(null);
    }
  }

  if (chargement) {
    return <Chargement libelle="Chargement des préférences…" />;
  }

  if (!form) {
    return (
      <Alerte ton="erreur">
        {erreur ?? "Impossible de charger les préférences de combinaisons."}
      </Alerte>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Combinaisons</h1>
        <p className="mt-1 text-xs text-texte-doux">
          Assemblages de sélections dont la cote totale tombe dans la fourchette
          visée. Les probabilités sont estimées par le modèle statistique et
          restent incertaines : aucune combinaison n&apos;est un conseil de
          pari.
        </p>
      </header>

      {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}
      {succes ? <Alerte ton="succes">{succes}</Alerte> : null}

      <form onSubmit={generer} className="flex flex-col gap-6">
        <Panneau
          titre="Critères de recherche"
          description="Valeurs préremplies depuis les paramètres. Les modifier ici ne change pas les préférences enregistrées."
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Champ label="Sélections" aide="Entre 2 et 15">
              <Saisie
                type="number"
                min={2}
                max={15}
                required
                value={form.nombre_selections}
                onChange={(e) =>
                  setForm({
                    ...form,
                    nombre_selections: Number(e.target.value),
                  })
                }
              />
            </Champ>
            <Champ label="Cote minimale">
              <Saisie
                type="number"
                min={1.01}
                max={10000}
                step="any"
                required
                value={form.cote_min}
                onChange={(e) =>
                  setForm({ ...form, cote_min: Number(e.target.value) })
                }
              />
            </Champ>
            <Champ label="Cote maximale">
              <Saisie
                type="number"
                min={1.02}
                max={10000}
                step="any"
                required
                value={form.cote_max}
                onChange={(e) =>
                  setForm({ ...form, cote_max: Number(e.target.value) })
                }
              />
            </Champ>
            <Champ label="Résultats" aide="Nombre maximal affiché">
              <Selection
                value={form.limite}
                onChange={(e) =>
                  setForm({ ...form, limite: Number(e.target.value) })
                }
              >
                {[5, 10, 20, 30, 50].map((valeur) => (
                  <option key={valeur} value={valeur}>
                    {valeur} combinaisons
                  </option>
                ))}
              </Selection>
            </Champ>
            <div className="flex items-end">
              <Bouton
                type="submit"
                variante="principal"
                className="w-full"
                disabled={calcul}
              >
                {calcul ? "Recherche…" : "Générer les combinaisons"}
              </Bouton>
            </div>
          </div>

          <div className="mt-4 flex flex-col gap-2">
            <p className="text-xs font-medium text-texte-doux">Marchés autorisés</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {marchesDisponibles.map((marche) => (
                <label
                  key={marche.code}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border border-bordure px-3 py-2 text-xs text-texte-doux transition hover:border-accent/40"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-cyan-400"
                    checked={form.marches_autorises.includes(marche.code)}
                    onChange={() => basculerMarche(marche.code)}
                  />
                  {marche.libelle}
                </label>
              ))}
            </div>
          </div>
        </Panneau>
      </form>

      {reponse ? (
        <div className="flex flex-col gap-4">
          <Panneau
            titre="Résultat de la recherche"
            description="Une combinaison contient une seule sélection par rencontre. La probabilité globale suppose les résultats indépendants."
          >
            <div className="flex flex-col gap-4">
              <Alerte ton="info">
                <p>{reponse.message}</p>
                <p className="mt-1">
                  {reponse.matchs_examines} rencontre(s) examinée(s),{" "}
                  {reponse.matchs_disponibles} exploitable(s),{" "}
                  {reponse.matchs_ignores} ignorée(s) ·{" "}
                  {reponse.selections_disponibles} sélection(s) disponible(s).
                </p>
              </Alerte>

              {reponse.recherche_tronquee ? (
                <Alerte ton="avertissement">
                  La recherche a atteint sa limite d&apos;exploration : des
                  combinaisons valides peuvent manquer. Réduisez le nombre de
                  sélections ou resserrez les critères.
                </Alerte>
              ) : null}

              {reponse.combinaisons.length === 0 ? (
                <EtatVide>
                  Aucune combinaison affichable. Ajoutez des rencontres à venir,
                  des cotes récentes et suffisamment de résultats passés, puis
                  élargissez la fourchette si nécessaire.
                </EtatVide>
              ) : (
                <div className="flex flex-col gap-3">
                  {reponse.combinaisons.map((combinaison, index) => {
                    const cle = cleCombinaison(combinaison);
                    return (
                      <CarteCombinaison
                        key={cle}
                        combinaison={combinaison}
                        rang={index + 1}
                        onEnregistrer={() => void enregistrer(combinaison)}
                        enregistrement={enregistrement === cle}
                        dejaEnregistree={enregistrees.has(cle)}
                      />
                    );
                  })}
                </div>
              )}

              <p className="text-[11px] leading-relaxed text-texte-faible">
                {reponse.avertissement}
              </p>
            </div>
          </Panneau>

          <Panneau
            titre="Comment lire ces résultats"
            description="Repères de lecture, sans recommandation de mise."
          >
            <ul className="flex flex-col gap-2 text-xs leading-relaxed text-texte-doux">
              <li>
                • La <span className="text-texte">cote totale</span> est le
                produit des cotes saisies pour chaque sélection.
              </li>
              <li>
                • La <span className="text-texte">probabilité estimée</span> est
                le produit des probabilités du modèle statistique ; la
                fourchette à 80 %
                reflète l&apos;incertitude du modèle, pas une garantie.
              </li>
              <li>
                • L&apos;<span className="text-texte">espérance estimée</span>{" "}
                vaut probabilité × cote totale − 1. Une valeur négative signifie
                que la marge du bookmaker reste défavorable sur cette
                combinaison.
              </li>
              <li>
                • Les rencontres sans historique suffisant ou sans cote récente
                sont ignorées et comptées ci-dessus.
              </li>
            </ul>
          </Panneau>
        </div>
      ) : null}
    </div>
  );
}
