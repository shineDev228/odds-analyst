"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export interface OptionCombobox {
  valeur: string;
  libelle: string;
}

/**
 * Sélecteur filtrable, pensé pour les longues listes (équipes, compétitions)
 * où un `<select>` natif ne permet pas de taper. Contrôlé : `valeur` est
 * l'identifiant sélectionné, `onChange` le renvoie.
 */
export function Combobox({
  valeur,
  onChange,
  options,
  placeholder = "Rechercher…",
  nom = "",
  erreur = false,
  vide = "Aucun résultat.",
}: {
  valeur: string;
  onChange: (valeur: string) => void;
  options: OptionCombobox[];
  placeholder?: string;
  nom?: string;
  erreur?: boolean;
  vide?: string;
}) {
  const [ouverte, setOuverte] = useState(false);
  const [requete, setRequete] = useState("");
  const [active, setActive] = useState(0);
  const racine = useRef<HTMLDivElement>(null);
  const champ = useRef<HTMLInputElement>(null);

  const selection = useMemo(
    () => options.find((option) => option.valeur === valeur) ?? null,
    [options, valeur],
  );

  const filtrees = useMemo(() => {
    const terme = requete.trim().toLowerCase();
    if (!terme) return options;
    return options.filter((option) => option.libelle.toLowerCase().includes(terme));
  }, [options, requete]);

  // Ferme la liste quand on clique ailleurs.
  useEffect(() => {
    function clicExterieur(evenement: MouseEvent) {
      if (racine.current && !racine.current.contains(evenement.target as Node)) {
        setOuverte(false);
      }
    }
    document.addEventListener("mousedown", clicExterieur);
    return () => document.removeEventListener("mousedown", clicExterieur);
  }, []);

  function choisir(optionValeur: string) {
    onChange(optionValeur);
    setOuverte(false);
    setRequete("");
  }

  function gererTouches(evenement: React.KeyboardEvent) {
    if (evenement.key === "ArrowDown") {
      evenement.preventDefault();
      setOuverte(true);
      setActive((courant) => Math.min(courant + 1, Math.max(filtrees.length - 1, 0)));
    } else if (evenement.key === "ArrowUp") {
      evenement.preventDefault();
      setActive((courant) => Math.max(courant - 1, 0));
    } else if (evenement.key === "Enter") {
      if (ouverte && filtrees[active]) {
        evenement.preventDefault();
        choisir(filtrees[active].valeur);
      }
    } else if (evenement.key === "Escape") {
      setOuverte(false);
    }
  }

  const texte = ouverte ? requete : (selection?.libelle ?? "");

  return (
    <div ref={racine} className="relative">
      <input
        ref={champ}
        type="text"
        role="combobox"
        aria-expanded={ouverte}
        aria-controls={nom ? `combobox-${nom}-liste` : undefined}
        aria-label={placeholder}
        aria-invalid={erreur || undefined}
        autoComplete="off"
        value={texte}
        placeholder={placeholder}
        onFocus={() => {
          setOuverte(true);
          setActive(0);
        }}
        onChange={(evenement) => {
          setOuverte(true);
          setRequete(evenement.target.value);
          setActive(0);
        }}
        onKeyDown={gererTouches}
        className={`w-full rounded-md border bg-fond px-3 py-2 text-sm text-texte placeholder:text-texte-faible focus:outline-none ${
          erreur ? "border-danger" : "border-bordure-forte focus:border-accent/60"
        }`}
      />
      {selection && !ouverte ? (
        <button
          type="button"
          tabIndex={-1}
          aria-label="Effacer la sélection"
          onClick={() => {
            onChange("");
            champ.current?.focus();
          }}
          className="absolute inset-y-0 right-2 flex items-center text-texte-faible transition hover:text-texte"
        >
          ×
        </button>
      ) : null}

      {ouverte ? (
        <ul
          id={nom ? `combobox-${nom}-liste` : undefined}
          role="listbox"
          className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-bordure-forte bg-fond-eleve py-1 shadow-lg shadow-black/40"
        >
          {filtrees.length === 0 ? (
            <li className="px-3 py-2 text-xs text-texte-faible">{vide}</li>
          ) : (
            filtrees.map((option, index) => (
              <li key={option.valeur} role="option" aria-selected={option.valeur === valeur}>
                <button
                  type="button"
                  onMouseDown={(evenement) => {
                    // Se déclenche avant le blur : on conserve la sélection.
                    evenement.preventDefault();
                    choisir(option.valeur);
                  }}
                  onMouseEnter={() => setActive(index)}
                  className={`block w-full truncate px-3 py-2 text-left text-sm transition ${
                    index === active ? "bg-accent/10 text-accent" : "text-texte-doux hover:text-texte"
                  }`}
                >
                  {option.libelle}
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
