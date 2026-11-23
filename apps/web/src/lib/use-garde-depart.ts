"use client";

import { useEffect } from "react";

/**
 * Avertit l'utilisateur qui quitte la page avec une saisie non enregistrée.
 * Ne couvre que la fermeture de l'onglet et le rechargement (navigation
 * native) ; la navigation interne est laissée aux boutons explicites.
 */
export function useGardeDepart(actif: boolean, message = "Des modifications ne sont pas enregistrées.") {
  useEffect(() => {
    if (!actif) return;
    const gerer = (evenement: BeforeUnloadEvent) => {
      evenement.preventDefault();
      evenement.returnValue = message;
      return message;
    };
    window.addEventListener("beforeunload", gerer);
    return () => window.removeEventListener("beforeunload", gerer);
  }, [actif, message]);
}
