"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

/** Composants partagés du système « Registre », alignés sur globals.css. */

export function EntetePage({
  titre,
  description,
  action,
}: {
  titre: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 pb-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-texte">{titre}</h1>
        {description ? (
          <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-texte-doux">
            {description}
          </p>
        ) : null}
      </div>
      {action}
    </header>
  );
}

export function Section({
  titre,
  description,
  action,
  children,
  className = "",
}: {
  titre: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`border-t border-bordure pt-5 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-medium text-texte">{titre}</h2>
          {description ? (
            <p className="mt-1 max-w-[72ch] text-xs leading-relaxed text-texte-doux">
              {description}
            </p>
          ) : null}
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Carte réservée aux formulaires et aux actions, pas aux données. */
export function Panneau({
  titre,
  description,
  action,
  children,
  className = "",
}: {
  titre: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-bordure bg-fond-panneau p-5 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-medium text-texte">{titre}</h2>
          {description ? (
            <p className="mt-1 max-w-[72ch] text-xs leading-relaxed text-texte-doux">
              {description}
            </p>
          ) : null}
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function Indicateur({
  libelle,
  valeur,
  aide,
  ton = "texte",
  className = "",
}: {
  libelle: string;
  valeur: string;
  aide?: string;
  ton?: "texte" | "neutre" | "accent" | "succes" | "danger";
  className?: string;
}) {
  const couleur =
    ton === "succes"
      ? "text-succes"
      : ton === "danger"
        ? "text-danger"
        : ton === "accent"
          ? "text-accent"
          : "text-texte";
  return (
    <div className={className}>
      <p className="text-xs leading-none text-texte-faible">{libelle}</p>
      <p className={`mt-1 font-mono text-lg tabular-nums ${couleur}`}>{valeur}</p>
      {aide ? <p className="mt-1 text-xs leading-snug text-texte-faible">{aide}</p> : null}
    </div>
  );
}

export function Tableau({
  children,
  className = "",
  minWidth = "680px",
}: {
  children: ReactNode;
  className?: string;
  minWidth?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table
        className={`w-full border-collapse text-left ${className}`}
        style={{ minWidth }}
      >
        {children}
      </table>
    </div>
  );
}

type VarianteBouton = "principal" | "secondaire" | "danger" | "discret";

const stylesBouton: Record<VarianteBouton, string> = {
  principal:
    "border-accent bg-accent text-fond hover:bg-accent/90 disabled:border-bordure disabled:bg-fond-eleve disabled:text-texte-faible",
  secondaire:
    "border-bordure-forte bg-fond-eleve text-texte hover:border-accent/50 hover:text-accent disabled:opacity-50",
  danger: "border-danger/40 bg-danger/10 text-danger hover:bg-danger/20 disabled:opacity-50",
  discret: "border-transparent text-texte-doux hover:text-texte disabled:opacity-50",
};

export function Bouton({
  variante = "secondaire",
  className = "",
  children,
  ref,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: VarianteBouton;
  ref?: React.Ref<HTMLButtonElement>;
}) {
  return (
    <button
      ref={ref}
      className={`inline-flex h-9 items-center justify-center gap-2 rounded-md border px-3 text-sm font-medium transition ${stylesBouton[variante]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Champ({
  label,
  aide,
  erreur,
  children,
  className = "",
}: {
  label: string;
  aide?: string;
  erreur?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label
      className={`flex flex-col gap-1.5 text-xs ${className}`}
      data-invalide={erreur ? "true" : undefined}
    >
      <span className="font-medium text-texte-doux">{label}</span>
      {children}
      {erreur ? (
        <span role="alert" className="text-xs leading-snug text-danger">
          {erreur}
        </span>
      ) : aide ? (
        <span className="text-xs leading-snug text-texte-faible">{aide}</span>
      ) : null}
    </label>
  );
}

const styleSaisie =
  "w-full rounded-md border border-bordure-forte bg-fond px-3 py-2 text-sm text-texte placeholder:text-texte-faible focus:border-accent/60 focus:outline-none";

export function Saisie({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`${styleSaisie} ${className}`} {...props} />;
}

export function Selection({
  className = "",
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`${styleSaisie} ${className}`} {...props}>
      {children}
    </select>
  );
}

export function ZoneTexte({
  className = "",
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`${styleSaisie} min-h-20 ${className}`} {...props} />;
}

export function Alerte({
  ton = "erreur",
  children,
}: {
  ton?: "erreur" | "succes" | "info" | "avertissement";
  children: ReactNode;
}) {
  const styles = {
    erreur: "border-danger/60 text-danger",
    succes: "border-succes/60 text-succes",
    info: "border-bordure-forte text-texte-doux",
    avertissement: "border-alerte/60 text-alerte",
  }[ton];

  return (
    <div
      role={ton === "erreur" ? "alert" : "status"}
      className={`border-l-2 py-1.5 pl-3 text-xs leading-relaxed ${styles}`}
    >
      {children}
    </div>
  );
}

export function EtatVide({ children }: { children: ReactNode }) {
  return (
    <p className="border-l-2 border-bordure-forte py-2 pl-3 text-xs leading-relaxed text-texte-faible">
      {children}
    </p>
  );
}

export function Badge({
  ton = "neutre",
  children,
}: {
  ton?: "neutre" | "accent" | "succes" | "alerte" | "danger";
  children: ReactNode;
}) {
  const styles = {
    neutre: "border-bordure-forte bg-fond-eleve text-texte-doux",
    accent: "border-accent/40 bg-accent/10 text-accent",
    succes: "border-succes/40 bg-succes/10 text-succes",
    alerte: "border-alerte/40 bg-alerte/10 text-alerte",
    danger: "border-danger/40 bg-danger/10 text-danger",
  }[ton];

  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${styles}`}
    >
      {children}
    </span>
  );
}

export function Chargement({ libelle = "Chargement…" }: { libelle?: string }) {
  return <p className="animate-pulse py-8 text-center text-xs text-texte-faible">{libelle}</p>;
}
