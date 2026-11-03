import type { ReactNode } from "react";

import { fr } from "@/messages/fr";

export function CadreAuth({
  titre,
  sousTitre,
  children,
  pied,
}: {
  titre: string;
  sousTitre: string;
  children: ReactNode;
  pied?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center px-5 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div
            aria-hidden
            className="flex size-11 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-sm font-semibold text-accent"
          >
            OA
          </div>
          <div>
            <p className="text-base font-semibold tracking-tight">{fr.app.nom}</p>
            <p className="text-xs text-texte-faible">{fr.app.sousTitre}</p>
          </div>
        </div>

        <div className="rounded-2xl border border-bordure bg-fond-panneau p-6">
          <h1 className="text-lg font-semibold tracking-tight">{titre}</h1>
          <p className="mt-1 text-xs text-texte-doux">{sousTitre}</p>
          <div className="mt-5">{children}</div>
        </div>

        <p className="mt-5 text-center text-[11px] leading-relaxed text-texte-faible">
          Outil d&apos;analyse statistique. Aucune prédiction n&apos;est présentée comme certaine,
          aucun pari n&apos;est placé automatiquement.
        </p>

        {pied ? <div className="mt-4 text-center text-xs text-texte-doux">{pied}</div> : null}
      </div>
    </div>
  );
}
