"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

/**
 * Notifications éphémères (toasts), montées une fois dans le layout racine.
 *
 * Un seul libellé par action : le bouton « Enregistrer » produit une
 * notification « Enregistré ». Les erreurs restent affichées en contexte
 * (près du formulaire) ; les succès passent par ici.
 */

type TonNotification = "succes" | "erreur" | "info";

interface Notification {
  id: number;
  ton: TonNotification;
  message: string;
}

interface ContexteNotifications {
  notifier: (ton: TonNotification, message: string) => void;
}

const Contexte = createContext<ContexteNotifications | null>(null);

const dureeAffichageMs = 5000;

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [liste, setListe] = useState<Notification[]>([]);
  const compteur = useRef(0);

  const notifier = useCallback((ton: TonNotification, message: string) => {
    const id = ++compteur.current;
    setListe((courant) => [...courant, { id, ton, message }]);
    window.setTimeout(() => {
      setListe((courant) => courant.filter((item) => item.id !== id));
    }, dureeAffichageMs);
  }, []);

  const valeur = useMemo(() => ({ notifier }), [notifier]);

  return (
    <Contexte.Provider value={valeur}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:items-end">
        {liste.map((item) => (
          <Toast key={item.id} notification={item} />
        ))}
      </div>
    </Contexte.Provider>
  );
}

function Toast({ notification }: { notification: Notification }) {
  const bordure = {
    succes: "border-succes",
    erreur: "border-danger",
    info: "border-bordure-forte",
  }[notification.ton];

  return (
    <div
      role={notification.ton === "erreur" ? "alert" : "status"}
      className={`pointer-events-auto w-full max-w-sm rounded-md border-l-2 bg-fond-eleve px-3 py-2 text-xs leading-relaxed text-texte shadow-lg shadow-black/50 ${bordure}`}
    >
      {notification.message}
    </div>
  );
}

export function useNotifications(): ContexteNotifications {
  const valeur = useContext(Contexte);
  if (!valeur) {
    throw new Error("useNotifications doit être utilisé dans <NotificationsProvider>.");
  }
  return valeur;
}
