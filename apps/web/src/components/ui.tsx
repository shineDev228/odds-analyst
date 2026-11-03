"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

/** Petits composants d'interface partagés, alignés sur les jetons de globals.css. */

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
    <section className={`rounded-2xl border border-bordure bg-fond-panneau p-5 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-texte">{titre}</h2>
          {description ? <p className="mt-1 text-xs text-texte-doux">{description}</p> : null}
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

type VarianteBouton = "principal" | "secondaire" | "danger" | "discret";

const stylesBouton: Record<VarianteBouton, string> = {
  principal:
    "border-accent/40 bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50",
  secondaire:
    "border-bordure-forte bg-fond-eleve text-texte hover:border-accent/40 hover:text-accent disabled:opacity-50",
  danger: "border-danger/40 bg-danger/10 text-danger hover:bg-danger/20 disabled:opacity-50",
  discret: "border-transparent text-texte-doux hover:text-texte disabled:opacity-50",
};

export function Bouton({
  variante = "secondaire",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: VarianteBouton }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition ${stylesBouton[variante]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Champ({
  label,
  aide,
  children,
  className = "",
}: {
  label: string;
  aide?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`flex flex-col gap-1.5 text-xs ${className}`}>
      <span className="font-medium text-texte-doux">{label}</span>
      {children}
      {aide ? <span className="text-[11px] text-texte-faible">{aide}</span> : null}
    </label>
  );
}

const styleSaisie =
  "w-full rounded-lg border border-bordure-forte bg-fond px-3 py-2 text-sm text-texte placeholder:text-texte-faible focus:border-accent/60 focus:outline-none";

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
    erreur: "border-danger/40 bg-danger/10 text-danger",
    succes: "border-succes/40 bg-succes/10 text-succes",
    info: "border-accent/30 bg-accent/5 text-texte-doux",
    avertissement: "border-alerte/30 bg-alerte/5 text-alerte",
  }[ton];

  return (
    <div className={`rounded-lg border px-3 py-2 text-xs leading-relaxed ${styles}`} role="status">
      {children}
    </div>
  );
}

export function EtatVide({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-bordure-forte px-4 py-6 text-center text-xs text-texte-faible">
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
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${styles}`}
    >
      {children}
    </span>
  );
}

export function Chargement({ libelle = "Chargement…" }: { libelle?: string }) {
  return <p className="animate-pulse py-6 text-center text-xs text-texte-faible">{libelle}</p>;
}
