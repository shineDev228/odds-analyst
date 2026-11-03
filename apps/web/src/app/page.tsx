import { fr } from "@/messages/fr";

const statutStyles: Record<string, string> = {
  "en-cours": "border-accent/40 bg-accent/10 text-accent",
  "a-venir": "border-bordure bg-fond-eleve text-texte-faible",
  termine: "border-succes/40 bg-succes/10 text-succes",
};

export default function PageAccueil() {
  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-5 py-10 sm:px-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div
            aria-hidden
            className="flex size-11 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-lg font-semibold text-accent"
          >
            OA
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{fr.app.nom}</h1>
            <p className="text-sm text-texte-doux">{fr.app.sousTitre}</p>
          </div>
        </div>

        <span className="w-fit rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
          Phase 0 — socle technique
        </span>
      </header>

      <section
        aria-labelledby="avertissement-titre"
        className="rounded-2xl border border-alerte/30 bg-alerte/5 p-5"
      >
        <h2 id="avertissement-titre" className="text-sm font-semibold text-alerte">
          {fr.avertissement.titre}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-texte-doux">{fr.avertissement.texte}</p>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section className="rounded-2xl border border-bordure bg-fond-panneau p-5">
          <h2 className="text-sm font-semibold text-texte">Avancement du projet</h2>
          <ol className="mt-4 space-y-2">
            {fr.phases.map((phase) => (
              <li
                key={phase.numero}
                className="flex items-center justify-between gap-4 rounded-lg border border-bordure/70 px-3 py-2"
              >
                <span className="flex items-baseline gap-3">
                  <span className="font-mono text-xs text-texte-faible">
                    {String(phase.numero).padStart(2, "0")}
                  </span>
                  <span className="text-sm text-texte">{phase.libelle}</span>
                </span>
                <span
                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                    statutStyles[phase.statut] ?? statutStyles["a-venir"]
                  }`}
                >
                  {fr.statuts[phase.statut as keyof typeof fr.statuts]}
                </span>
              </li>
            ))}
          </ol>
        </section>

        <div className="flex flex-col gap-6">
          <section className="rounded-2xl border border-bordure bg-fond-panneau p-5">
            <h2 className="text-sm font-semibold text-texte">Services</h2>
            <ul className="mt-4 space-y-3 text-sm">
              <li>
                <a
                  className="group flex items-center justify-between rounded-lg border border-bordure/70 px-3 py-2 transition hover:border-accent/40 hover:bg-fond-eleve"
                  href="http://localhost:8000/docs"
                  rel="noreferrer"
                  target="_blank"
                >
                  <span className="text-texte">Documentation de l&apos;API</span>
                  <span className="font-mono text-xs text-texte-faible group-hover:text-accent">
                    :8000/docs
                  </span>
                </a>
              </li>
              <li>
                <a
                  className="group flex items-center justify-between rounded-lg border border-bordure/70 px-3 py-2 transition hover:border-accent/40 hover:bg-fond-eleve"
                  href="http://localhost:8000/api/v1/health"
                  rel="noreferrer"
                  target="_blank"
                >
                  <span className="text-texte">État de la base de données</span>
                  <span className="font-mono text-xs text-texte-faible group-hover:text-accent">
                    /health
                  </span>
                </a>
              </li>
            </ul>
          </section>

          <section className="rounded-2xl border border-bordure bg-fond-panneau p-5">
            <h2 className="text-sm font-semibold text-texte">Principe directeur</h2>
            <p className="mt-3 text-sm leading-relaxed text-texte-doux">
              Chaque probabilité affichée par ODDS ANALYST sera accompagnée d&apos;une fourchette
              et d&apos;une note de confiance. Aucune estimation ne sera présentée comme une
              certitude.
            </p>
          </section>
        </div>
      </div>

      <footer className="mt-auto border-t border-bordure/70 pt-5 text-xs text-texte-faible">
        <p>
          Usage strictement personnel. Aucun scraping non autorisé, aucun stockage
          d&apos;identifiants de bookmaker, aucun placement automatique de pari.
        </p>
      </footer>
    </div>
  );
}
