/** Formatage francophone des dates et des nombres. */

const formateurDateHeure = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
});

const formateurDate = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" });

const formateurNombre = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });

export function formatDateHeure(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return formateurDateHeure.format(date);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "—";
  return formateurDate.format(date);
}

export function formatNombre(valeur: number | null | undefined): string {
  if (valeur === null || valeur === undefined) return "—";
  return formateurNombre.format(valeur);
}

/**
 * Convertit une date ISO en valeur acceptée par `<input type="datetime-local">`
 * en tenant compte du fuseau du navigateur.
 */
export function versDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const decalage = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - decalage).toISOString().slice(0, 16);
}

/** Valeur par défaut : aujourd'hui à 20 h 45, heure locale. */
export function datetimeLocalParDefaut(): string {
  const date = new Date();
  date.setHours(20, 45, 0, 0);
  return versDatetimeLocal(date.toISOString());
}
