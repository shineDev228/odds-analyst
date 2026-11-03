/**
 * Client HTTP de l'interface.
 *
 * Les requêtes passent par le proxy Next.js (`/api` → API FastAPI, voir
 * next.config.ts) afin de rester en même origine : les cookies de session
 * et de sécurité CSRF fonctionnent alors sans configuration CORS.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const CSRF_COOKIE = "odds_analyst_csrf";

export interface DetailErreur {
  champ: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly details: DetailErreur[];

  constructor(status: number, message: string, details: DetailErreur[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function lireCookie(nom: string): string | null {
  if (typeof document === "undefined") return null;
  const prefixe = `${nom}=`;
  for (const morceau of document.cookie.split(";")) {
    const valeur = morceau.trim();
    if (valeur.startsWith(prefixe)) {
      return decodeURIComponent(valeur.slice(prefixe.length));
    }
  }
  return null;
}

interface OptionsRequete {
  methode?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  corps?: unknown;
  /** Désactive la redirection automatique vers /connexion en cas de 401. */
  anonyme?: boolean;
}

export async function apiFetch<T>(chemin: string, options: OptionsRequete = {}): Promise<T> {
  const methode = options.methode ?? (options.corps === undefined ? "GET" : "POST");
  const entetes: Record<string, string> = { Accept: "application/json" };

  if (options.corps !== undefined) {
    entetes["Content-Type"] = "application/json";
  }

  if (methode !== "GET") {
    const jeton = lireCookie(CSRF_COOKIE);
    if (jeton) entetes["X-CSRF-Token"] = jeton;
  }

  let reponse: Response;
  try {
    reponse = await fetch(`${BASE}${chemin}`, {
      method: methode,
      headers: entetes,
      credentials: "include",
      cache: "no-store",
      body: options.corps === undefined ? undefined : JSON.stringify(options.corps),
    });
  } catch {
    throw new ApiError(
      0,
      "Impossible de joindre l'API. Vérifiez que le serveur est démarré sur le port 8000.",
    );
  }

  if (reponse.status === 204) {
    return undefined as T;
  }

  const texte = await reponse.text();
  let donnees: unknown = null;
  if (texte) {
    try {
      donnees = JSON.parse(texte);
    } catch {
      donnees = null;
    }
  }

  if (!reponse.ok) {
    const payload = (donnees ?? {}) as {
      detail?: string;
      title?: string;
      errors?: DetailErreur[];
    };

    if (reponse.status === 401 && !options.anonyme && typeof window !== "undefined") {
      window.location.href = "/connexion";
    }

    throw new ApiError(
      reponse.status,
      payload.detail ?? payload.title ?? `Erreur ${reponse.status}.`,
      payload.errors ?? [],
    );
  }

  return donnees as T;
}

/** Message lisible pour l'utilisateur, quel que soit le type d'erreur. */
export function messageErreur(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.details.length > 0) {
      return error.details.map((item) => `${item.champ} : ${item.message}`).join(" · ");
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Une erreur inattendue est survenue.";
}
