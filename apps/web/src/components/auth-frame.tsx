import type { ReactNode } from "react";

import { fr } from "@/messages/fr";

function Marque() {
  return (
    <div className="flex items-center gap-3">
      <div
        aria-hidden
        className="flex size-9 items-center justify-center rounded-md border border-accent/50 text-sm font-semibold text-accent"
      >
        OA
      </div>
      <div>
        <p className="text-sm font-semibold tracking-tight">{fr.app.nom}</p>
        <p className="text-xs text-texte-faible">{fr.app.sousTitre}</p>
      </div>
    </div>
  );
}

function ExempleCote() {
  const cotes = [
    { code: "1", valeur: "2,10", probabilite: "48 %" },
    { code: "X", valeur: "3,40", probabilite: "27 %" },
    { code: "2", valeur: "3,20", probabilite: "25 %" },
  ];
  return (
    <div className="mt-10 border-t border-bordure pt-6">
      <p className="text-xs text-texte-faible">Exemple de lecture</p>
      <p className="mt-1 text-sm text-texte">Paris — Marseille</p>
      <div className="mt-3 grid grid-cols-3 gap-4">
        {cotes.map((cote) => (
          <div key={cote.code}>
            <p className="text-xs text-texte-faible">{cote.code}</p>
            <p className="font-mono text-2xl tabular-nums text-texte">{cote.valeur}</p>
            <p className="text-xs text-texte-doux">{cote.probabilite}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

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
    <div className="grid min-h-screen md:grid-cols-[minmax(0,1fr)_420px]">
      <aside className="hidden flex-col justify-between border-r border-bordure p-8 md:flex xl:p-14">
        <Marque />

        <div>
          <p className="max-w-[26ch] text-2xl font-medium leading-snug tracking-tight text-texte">
            Chaque probabilité est une estimation. La fourchette fait partie de la réponse.
          </p>
          <p className="mt-4 max-w-[44ch] text-sm leading-relaxed text-texte-doux">
            Un poste de travail pour lire les rencontres, comparer les cotes et suivre la
            calibration du modèle — sans jamais présenter un résultat comme certain.
          </p>
          <ExempleCote />
        </div>

        <p className="max-w-[44ch] text-xs leading-relaxed text-texte-faible">
          Outil d&apos;analyse statistique. Aucun pari n&apos;est placé automatiquement.
        </p>
      </aside>

      <main className="flex items-center justify-center px-5 py-10 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 md:hidden">
            <Marque />
          </div>

          <h1 className="text-2xl font-semibold tracking-tight text-texte">{titre}</h1>
          <p className="mt-1 text-sm leading-relaxed text-texte-doux">{sousTitre}</p>

          <div className="mt-6 border-t border-bordure pt-6">{children}</div>

          {pied ? <div className="mt-5 text-center text-xs text-texte-doux">{pied}</div> : null}
        </div>
      </main>
    </div>
  );
}
