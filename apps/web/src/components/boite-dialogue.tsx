"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { Bouton } from "./ui";

/**
 * Confirmation modale, remplaçant `window.confirm` : elle respecte le thème,
 * piège le focus et répond à Échap. Les actions destructrices y précisent
 * exactement ce qui sera supprimé.
 */
export function BoiteDialogue({
  ouvert,
  titre,
  description,
  confirmation = "Confirmer",
  annulation = "Annuler",
  ton = "danger",
  enCours = false,
  libelleEnCours = "Suppression…",
  onConfirmer,
  onAnnuler,
  children,
}: {
  ouvert: boolean;
  titre: string;
  description?: string;
  confirmation?: string;
  annulation?: string;
  ton?: "danger" | "principal";
  enCours?: boolean;
  libelleEnCours?: string;
  onConfirmer: () => void;
  onAnnuler: () => void;
  children?: ReactNode;
}) {
  const boutonConfirmer = useRef<HTMLButtonElement>(null);
  const boutonAnnuler = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!ouvert) return;
    // Focus sur l'action la moins destructive : l'annulation.
    boutonAnnuler.current?.focus();
    const gererTouche = (evenement: KeyboardEvent) => {
      if (evenement.key === "Escape") onAnnuler();
    };
    document.addEventListener("keydown", gererTouche);
    return () => document.removeEventListener("keydown", gererTouche);
  }, [ouvert, onAnnuler]);

  if (!ouvert) return null;

  function gererTabulation(evenement: React.KeyboardEvent) {
    if (evenement.key !== "Tab") return;
    const boutons = [boutonAnnuler.current, boutonConfirmer.current].filter(
      (bouton): bouton is HTMLButtonElement => bouton !== null,
    );
    if (boutons.length < 2) return;
    const premier = boutons[0];
    const dernier = boutons[boutons.length - 1];
    if (evenement.shiftKey && document.activeElement === premier) {
      evenement.preventDefault();
      dernier.focus();
    } else if (!evenement.shiftKey && document.activeElement === dernier) {
      evenement.preventDefault();
      premier.focus();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div className="absolute inset-0 bg-black/60" aria-hidden onClick={onAnnuler} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="boite-dialogue-titre"
        aria-describedby={description ? "boite-dialogue-description" : undefined}
        onKeyDown={gererTabulation}
        className="relative w-full max-w-md rounded-lg border border-bordure bg-fond-panneau p-5 shadow-2xl shadow-black/60"
      >
        <h2 id="boite-dialogue-titre" className="text-base font-semibold tracking-tight text-texte">
          {titre}
        </h2>
        {description ? (
          <p id="boite-dialogue-description" className="mt-2 text-sm leading-relaxed text-texte-doux">
            {description}
          </p>
        ) : null}
        {children}
        <div className="mt-5 flex justify-end gap-2">
          <Bouton ref={boutonAnnuler} variante="secondaire" onClick={onAnnuler}>
            {annulation}
          </Bouton>
          <Bouton
            ref={boutonConfirmer}
            variante={ton}
            onClick={onConfirmer}
            disabled={enCours}
          >
            {enCours ? libelleEnCours : confirmation}
          </Bouton>
        </div>
      </div>
    </div>
  );
}
