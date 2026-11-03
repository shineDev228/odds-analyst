"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CadreAuth } from "@/components/auth-frame";
import { Alerte, Bouton, Champ, Saisie } from "@/components/ui";
import { apiFetch, messageErreur } from "@/lib/api";
import type { EtatAuth } from "@/lib/types";

export default function PagePremiereUtilisation() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [verification, setVerification] = useState(true);

  useEffect(() => {
    let actif = true;
    void (async () => {
      try {
        const statut = await apiFetch<EtatAuth>("/v1/auth/status", { anonyme: true });
        if (!actif) return;
        if (statut.authenticated) {
          router.replace("/tableau-de-bord");
          return;
        }
        if (statut.admin_configured) {
          router.replace("/connexion");
          return;
        }
      } catch {
        // On laisse le formulaire s'afficher : l'erreur remontera à l'envoi.
      } finally {
        if (actif) setVerification(false);
      }
    })();
    return () => {
      actif = false;
    };
  }, [router]);

  async function soumettre(evenement: React.FormEvent<HTMLFormElement>) {
    evenement.preventDefault();
    setErreur(null);

    if (motDePasse !== confirmation) {
      setErreur("Les deux mots de passe saisis ne correspondent pas.");
      return;
    }

    setEnvoi(true);
    try {
      await apiFetch("/v1/auth/bootstrap", {
        methode: "POST",
        corps: { email, password: motDePasse },
        anonyme: true,
      });
      router.replace("/tableau-de-bord");
      router.refresh();
    } catch (error) {
      setErreur(messageErreur(error));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <CadreAuth
      titre="Première utilisation"
      sousTitre="Créez l'unique compte administrateur de cette installation. Cette étape n'est possible qu'une seule fois."
    >
      {verification ? (
        <p className="animate-pulse text-center text-xs text-texte-faible">
          Vérification de l&apos;installation…
        </p>
      ) : (
        <form onSubmit={soumettre} className="flex flex-col gap-4">
          <Champ label="Adresse électronique">
            <Saisie
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="vous@exemple.fr"
            />
          </Champ>

          <Champ
            label="Mot de passe"
            aide="Au moins 12 caractères, avec des caractères variés."
          >
            <Saisie
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
            />
          </Champ>

          <Champ label="Confirmation du mot de passe">
            <Saisie
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
          </Champ>

          {erreur ? <Alerte ton="erreur">{erreur}</Alerte> : null}

          <Bouton type="submit" variante="principal" disabled={envoi} className="mt-1 py-2.5">
            {envoi ? "Création…" : "Créer le compte et se connecter"}
          </Bouton>
        </form>
      )}
    </CadreAuth>
  );
}
