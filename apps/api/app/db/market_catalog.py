"""Catalogue des marchés.

Chaque entrée décrit un *modèle* de marché : famille, période, sujet, type de
ligne et sélections par défaut. Le catalogue couvre les grandes familles 1xBet ;
toute variante absente peut être saisie comme marché personnalisé, sans
migration.

Les codes sont stables et préfixés par le sport. Ne jamais réutiliser un code
pour un autre marché : cela changerait le sens des données historiques.
"""

from typing import Any

MarketDefinition = dict[str, Any]


def _sel(code: str, label: str) -> dict[str, str]:
    return {"code": code, "label": label}


def _market(
    sport: str,
    code: str,
    name: str,
    family: str,
    selections: list[dict[str, str]],
    *,
    period: str = "match",
    subject: str = "match",
    line_kind: str = "aucune",
    description: str | None = None,
) -> MarketDefinition:
    return {
        "code": f"{sport}.{code}",
        "sport_code": sport,
        "name": name,
        "family": family,
        "period": period,
        "subject": subject,
        "line_kind": line_kind,
        "selection_templates": selections,
        "description": description,
    }


RESULT = [_sel("1", "Domicile"), _sel("X", "Match nul"), _sel("2", "Extérieur")]
DOUBLE_CHANCE = [
    _sel("1X", "Domicile ou nul"),
    _sel("12", "Domicile ou extérieur"),
    _sel("X2", "Nul ou extérieur"),
]
OVER_UNDER = [_sel("plus", "Plus"), _sel("moins", "Moins")]
YES_NO = [_sel("oui", "Oui"), _sel("non", "Non")]
HANDICAP = [_sel("1", "Domicile"), _sel("2", "Extérieur")]
EXACT_SCORE = [
    *[_sel(f"{home}_{away}", f"{home}-{away}") for home in range(4) for away in range(4)],
    _sel("autre", "Autre score"),
]
EXACT_SCORE_HALF = [
    *[_sel(f"{home}_{away}", f"{home}-{away}") for home in range(3) for away in range(3)],
    _sel("autre", "Autre score"),
]


def _football_catalog() -> list[MarketDefinition]:
    items: list[MarketDefinition] = []

    # --- Résultat et double chance -----------------------------------------
    items += [
        _market("football", "resultat_1x2", "Résultat (temps réglementaire)", "resultat", RESULT),
        _market(
            "football",
            "resultat_1x2_mt",
            "Résultat à la mi-temps",
            "resultat",
            RESULT,
            period="mi_temps",
        ),
        _market(
            "football",
            "resultat_1x2_2mt",
            "Résultat de la 2e mi-temps",
            "resultat",
            RESULT,
            period="seconde_mi_temps",
        ),
        _market(
            "football",
            "resultat_sans_nul",
            "Résultat sans match nul",
            "resultat",
            [_sel("12", "Domicile ou extérieur")],
        ),
        _market("football", "double_chance", "Double chance", "double_chance", DOUBLE_CHANCE),
        _market(
            "football",
            "double_chance_mt",
            "Double chance à la mi-temps",
            "double_chance",
            DOUBLE_CHANCE,
            period="mi_temps",
        ),
        _market(
            "football",
            "resultat_mi_temps_fin",
            "Mi-temps / fin de match",
            "resultat",
            [
                _sel("1_1", "1 / 1"),
                _sel("1_X", "1 / X"),
                _sel("1_2", "1 / 2"),
                _sel("X_1", "X / 1"),
                _sel("X_X", "X / X"),
                _sel("X_2", "X / 2"),
                _sel("2_1", "2 / 1"),
                _sel("2_X", "2 / X"),
                _sel("2_2", "2 / 2"),
            ],
        ),
        _market(
            "football",
            "equipe_gagne_les_deux_mi_temps",
            "Une équipe gagne les deux mi-temps",
            "resultat",
            [
                _sel("domicile", "Domicile"),
                _sel("exterieur", "Extérieur"),
                _sel("aucune", "Aucune"),
            ],
        ),
        _market(
            "football",
            "resultat_prolongation",
            "Résultat en prolongation",
            "resultat",
            RESULT,
            period="prolongation",
        ),
        _market(
            "football",
            "qualification",
            "Qualification",
            "resultat",
            [_sel("domicile", "Domicile"), _sel("exterieur", "Extérieur")],
            period="prolongation",
        ),
        _market(
            "football",
            "vainqueur_tirs_au_but",
            "Vainqueur aux tirs au but",
            "resultat",
            [_sel("domicile", "Domicile"), _sel("exterieur", "Extérieur")],
            period="tirs_au_but",
        ),
        _market(
            "football", "resultat_apres_90_min", "Résultat après 90 minutes", "resultat", RESULT
        ),
        _market(
            "football",
            "resultat_apres_120_min",
            "Résultat après 120 minutes",
            "resultat",
            RESULT,
            period="prolongation",
        ),
    ]

    # --- Handicaps ----------------------------------------------------------
    items += [
        _market(
            "football",
            "handicap_asiatique",
            "Handicap asiatique",
            "handicap",
            HANDICAP,
            line_kind="simple",
        ),
        _market(
            "football",
            "handicap_asiatique_mt",
            "Handicap asiatique (mi-temps)",
            "handicap",
            HANDICAP,
            period="mi_temps",
            line_kind="simple",
        ),
        _market(
            "football",
            "handicap_europeen",
            "Handicap européen",
            "handicap",
            [_sel("1", "Domicile"), _sel("X", "Nul"), _sel("2", "Extérieur")],
            line_kind="simple",
        ),
        _market(
            "football",
            "handicap_equipe_domicile",
            "Handicap équipe à domicile",
            "handicap",
            [_sel("plus", "Plus"), _sel("moins", "Moins")],
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "handicap_equipe_exterieur",
            "Handicap équipe à l'extérieur",
            "handicap",
            [_sel("plus", "Plus"), _sel("moins", "Moins")],
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "handicap_corners",
            "Handicap corners",
            "corners",
            HANDICAP,
            line_kind="simple",
        ),
        _market(
            "football",
            "handicap_cartons",
            "Handicap cartons",
            "cartons",
            HANDICAP,
            line_kind="simple",
        ),
    ]

    # --- Totaux de buts -----------------------------------------------------
    items += [
        _market(
            "football", "total_buts", "Total de buts", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "football",
            "total_buts_mt",
            "Total de buts (mi-temps)",
            "totaux",
            OVER_UNDER,
            period="mi_temps",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_buts_2mt",
            "Total de buts (2e mi-temps)",
            "totaux",
            OVER_UNDER,
            period="seconde_mi_temps",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_buts_domicile",
            "Total de buts de l'équipe à domicile",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_buts_exterieur",
            "Total de buts de l'équipe à l'extérieur",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_buts_pair_impair",
            "Total de buts pair / impair",
            "totaux",
            [_sel("pair", "Pair"), _sel("impair", "Impair")],
        ),
        _market(
            "football",
            "total_buts_intervalle",
            "Total de buts par intervalle",
            "totaux",
            [
                _sel("0_1", "0 à 1 but"),
                _sel("2_3", "2 à 3 buts"),
                _sel("4_5", "4 à 5 buts"),
                _sel("6_plus", "6 buts ou plus"),
            ],
        ),
        _market(
            "football",
            "total_buts_exact",
            "Nombre exact de buts",
            "totaux",
            [
                _sel("0", "0"),
                _sel("1", "1"),
                _sel("2", "2"),
                _sel("3", "3"),
                _sel("4", "4"),
                _sel("5", "5"),
                _sel("6_plus", "6 ou plus"),
            ],
        ),
        _market(
            "football",
            "total_buts_prolongation",
            "Total de buts en prolongation",
            "totaux",
            OVER_UNDER,
            period="prolongation",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_buts_apres_120_min",
            "Total de buts après 120 minutes",
            "totaux",
            OVER_UNDER,
            period="prolongation",
            line_kind="simple",
        ),
    ]

    # --- Les deux équipes marquent -----------------------------------------
    items += [
        _market("football", "btts", "Les deux équipes marquent", "btts", YES_NO),
        _market(
            "football",
            "btts_mt",
            "Les deux équipes marquent (mi-temps)",
            "btts",
            YES_NO,
            period="mi_temps",
        ),
        _market(
            "football",
            "btts_2mt",
            "Les deux équipes marquent (2e mi-temps)",
            "btts",
            YES_NO,
            period="seconde_mi_temps",
        ),
        _market(
            "football",
            "equipe_domicile_marque",
            "L'équipe à domicile marque",
            "btts",
            YES_NO,
            subject="team",
        ),
        _market(
            "football",
            "equipe_exterieur_marque",
            "L'équipe à l'extérieur marque",
            "btts",
            YES_NO,
            subject="team",
        ),
        _market(
            "football",
            "les_deux_equipes_marquent_deux_buts",
            "Les deux équipes marquent au moins deux buts",
            "btts",
            YES_NO,
        ),
        _market(
            "football",
            "btts_et_resultat",
            "Les deux équipes marquent et résultat",
            "combine",
            [
                _sel("oui_1", "Oui / Domicile"),
                _sel("oui_X", "Oui / Nul"),
                _sel("oui_2", "Oui / Extérieur"),
                _sel("non_1", "Non / Domicile"),
                _sel("non_X", "Non / Nul"),
                _sel("non_2", "Non / Extérieur"),
            ],
        ),
        _market(
            "football",
            "btts_et_total",
            "Les deux équipes marquent et total de buts",
            "combine",
            [
                _sel("oui_plus", "Oui / Plus"),
                _sel("oui_moins", "Oui / Moins"),
                _sel("non_plus", "Non / Plus"),
                _sel("non_moins", "Non / Moins"),
            ],
            line_kind="double",
        ),
    ]

    # --- Scores exacts et périodes -----------------------------------------
    items += [
        _market("football", "score_exact", "Score exact", "score_exact", EXACT_SCORE),
        _market(
            "football",
            "score_exact_mt",
            "Score exact à la mi-temps",
            "score_exact",
            EXACT_SCORE_HALF,
            period="mi_temps",
        ),
        _market(
            "football",
            "score_exact_2mt",
            "Score exact de la 2e mi-temps",
            "score_exact",
            EXACT_SCORE_HALF,
            period="seconde_mi_temps",
        ),
        _market(
            "football",
            "score_exact_fin_de_match",
            "Score exact et résultat final",
            "score_exact",
            EXACT_SCORE,
        ),
        _market(
            "football",
            "score_apres_15_min",
            "Score après 15 minutes",
            "score_exact",
            EXACT_SCORE_HALF,
            period="15_min",
        ),
        _market(
            "football",
            "score_apres_30_min",
            "Score après 30 minutes",
            "score_exact",
            EXACT_SCORE_HALF,
            period="30_min",
        ),
        _market(
            "football",
            "score_apres_60_min",
            "Score après 60 minutes",
            "score_exact",
            EXACT_SCORE_HALF,
            period="60_min",
        ),
        _market(
            "football",
            "score_apres_75_min",
            "Score après 75 minutes",
            "score_exact",
            EXACT_SCORE_HALF,
            period="75_min",
        ),
        _market(
            "football",
            "mi_temps_la_plus_prolifique",
            "Mi-temps la plus prolifique",
            "score_exact",
            [
                _sel("premiere", "1re mi-temps"),
                _sel("seconde", "2e mi-temps"),
                _sel("egales", "Autant de buts"),
            ],
        ),
        _market(
            "football",
            "equipe_marque_plus_de_buts_en_2e_mi_temps",
            "Plus de buts en 2e mi-temps",
            "score_exact",
            [
                _sel("oui", "Oui"),
                _sel("non", "Non"),
            ],
        ),
    ]

    # --- Temps de marquage --------------------------------------------------
    items += [
        _market(
            "football", "but_dans_les_deux_mi_temps", "But dans les deux mi-temps", "temps", YES_NO
        ),
        _market("football", "but_avant_30_min", "But avant la 30e minute", "temps", YES_NO),
        _market("football", "but_apres_75_min", "But après la 75e minute", "temps", YES_NO),
        _market(
            "football",
            "premier_but_avant_10_min",
            "Premier but avant la 10e minute",
            "temps",
            YES_NO,
        ),
        _market(
            "football",
            "temps_du_premier_but",
            "Temps du premier but",
            "temps",
            [
                _sel("0_10", "0 à 10 min"),
                _sel("11_20", "11 à 20 min"),
                _sel("21_30", "21 à 30 min"),
                _sel("31_40", "31 à 40 min"),
                _sel("41_45", "41 à 45 min"),
                _sel("46_60", "46 à 60 min"),
                _sel("61_75", "61 à 75 min"),
                _sel("76_90", "76 à 90 min"),
                _sel("aucun", "Aucun but"),
            ],
        ),
        _market(
            "football",
            "premiere_equipe_marquer",
            "Première équipe à marquer",
            "temps",
            [
                _sel("domicile", "Domicile"),
                _sel("exterieur", "Extérieur"),
                _sel("aucune", "Aucune"),
            ],
        ),
        _market(
            "football",
            "derniere_equipe_marquer",
            "Dernière équipe à marquer",
            "temps",
            [
                _sel("domicile", "Domicile"),
                _sel("exterieur", "Extérieur"),
                _sel("aucune", "Aucune"),
            ],
        ),
        _market(
            "football",
            "method_du_premier_but",
            "Méthode du premier but",
            "temps",
            [
                _sel("pied", "Du pied"),
                _sel("tete", "De la tête"),
                _sel("penalty", "Penalty"),
                _sel("coup_franc", "Coup franc"),
                _sel("contre_camp", "Contre son camp"),
                _sel("aucun", "Aucun but"),
            ],
        ),
        _market(
            "football",
            "equipe_marque_dans_les_deux_mi_temps",
            "Une équipe marque dans les deux mi-temps",
            "temps",
            [
                _sel("domicile", "Domicile"),
                _sel("exterieur", "Extérieur"),
                _sel("les_deux", "Les deux"),
                _sel("aucune", "Aucune"),
            ],
        ),
    ]

    # --- Corners ------------------------------------------------------------
    items += [
        _market(
            "football",
            "total_corners",
            "Total de corners",
            "corners",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "football",
            "total_corners_mt",
            "Total de corners (mi-temps)",
            "corners",
            OVER_UNDER,
            period="mi_temps",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_corners_domicile",
            "Total de corners de l'équipe à domicile",
            "corners",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_corners_exterieur",
            "Total de corners de l'équipe à l'extérieur",
            "corners",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_corners_intervalle",
            "Total de corners par intervalle",
            "corners",
            [
                _sel("0_8", "0 à 8"),
                _sel("9_11", "9 à 11"),
                _sel("12_plus", "12 ou plus"),
            ],
        ),
        _market(
            "football",
            "premier_corner",
            "Premier corner",
            "corners",
            [_sel("domicile", "Domicile"), _sel("exterieur", "Extérieur")],
        ),
        _market(
            "football",
            "dernier_corner",
            "Dernier corner",
            "corners",
            [_sel("domicile", "Domicile"), _sel("exterieur", "Extérieur")],
        ),
        _market(
            "football",
            "course_aux_corners",
            "Course aux corners",
            "corners",
            [
                _sel("domicile", "Domicile"),
                _sel("exterieur", "Extérieur"),
                _sel("egalite", "Égalité"),
            ],
        ),
        _market(
            "football",
            "nombre_exact_corners",
            "Nombre exact de corners",
            "corners",
            [
                _sel("0_4", "0 à 4"),
                _sel("5_7", "5 à 7"),
                _sel("8_10", "8 à 10"),
                _sel("11_13", "11 à 13"),
                _sel("14_plus", "14 ou plus"),
            ],
        ),
    ]

    # --- Cartons ------------------------------------------------------------
    items += [
        _market(
            "football",
            "total_cartons",
            "Total de cartons",
            "cartons",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "football",
            "total_cartons_mt",
            "Total de cartons (mi-temps)",
            "cartons",
            OVER_UNDER,
            period="mi_temps",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_cartons_domicile",
            "Total de cartons de l'équipe à domicile",
            "cartons",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_cartons_exterieur",
            "Total de cartons de l'équipe à l'extérieur",
            "cartons",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_cartons_jaunes",
            "Total de cartons jaunes",
            "cartons",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "football",
            "total_cartons_rouges",
            "Total de cartons rouges",
            "cartons",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market("football", "carton_rouge", "Un carton rouge est distribué", "cartons", YES_NO),
        _market(
            "football",
            "premier_carton",
            "Premier carton",
            "cartons",
            [_sel("domicile", "Domicile"), _sel("exterieur", "Extérieur")],
        ),
        _market(
            "football",
            "dernier_carton",
            "Dernier carton",
            "cartons",
            [_sel("domicile", "Domicile"), _sel("exterieur", "Extérieur")],
        ),
        _market(
            "football",
            "total_cartons_intervalle",
            "Total de cartons par intervalle",
            "cartons",
            [
                _sel("0_2", "0 à 2"),
                _sel("3_4", "3 à 4"),
                _sel("5_6", "5 à 6"),
                _sel("7_plus", "7 ou plus"),
            ],
        ),
        _market(
            "football",
            "nombre_exact_cartons",
            "Nombre exact de cartons",
            "cartons",
            [
                _sel("0", "0"),
                _sel("1", "1"),
                _sel("2", "2"),
                _sel("3", "3"),
                _sel("4", "4"),
                _sel("5", "5"),
                _sel("6_plus", "6 ou plus"),
            ],
        ),
    ]

    # --- Tirs et statistiques ----------------------------------------------
    items += [
        _market("football", "total_tirs", "Total de tirs", "tirs", OVER_UNDER, line_kind="simple"),
        _market(
            "football",
            "total_tirs_cadres",
            "Total de tirs cadrés",
            "tirs",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "football",
            "total_tirs_domicile",
            "Total de tirs de l'équipe à domicile",
            "tirs",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_tirs_exterieur",
            "Total de tirs de l'équipe à l'extérieur",
            "tirs",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_tirs_cadres_domicile",
            "Total de tirs cadrés de l'équipe à domicile",
            "tirs",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_tirs_cadres_exterieur",
            "Total de tirs cadrés de l'équipe à l'extérieur",
            "tirs",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_hors_jeu",
            "Total de hors-jeu",
            "statistiques",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "football",
            "total_fautes",
            "Total de fautes",
            "statistiques",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "football",
            "total_fautes_domicile",
            "Total de fautes de l'équipe à domicile",
            "statistiques",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "total_fautes_exterieur",
            "Total de fautes de l'équipe à l'extérieur",
            "statistiques",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football",
            "possession_domicile",
            "Possession de l'équipe à domicile",
            "statistiques",
            [
                _sel("0_40", "Moins de 40 %"),
                _sel("40_50", "40 à 50 %"),
                _sel("50_60", "50 à 60 %"),
                _sel("60_plus", "Plus de 60 %"),
            ],
        ),
        _market(
            "football",
            "possession_exterieur",
            "Possession de l'équipe à l'extérieur",
            "statistiques",
            [
                _sel("0_40", "Moins de 40 %"),
                _sel("40_50", "40 à 50 %"),
                _sel("50_60", "50 à 60 %"),
                _sel("60_plus", "Plus de 60 %"),
            ],
        ),
        _market(
            "football",
            "plus_de_tirs_cadres",
            "Équipe avec le plus de tirs cadrés",
            "tirs",
            [
                _sel("domicile", "Domicile"),
                _sel("exterieur", "Extérieur"),
                _sel("egalite", "Égalité"),
            ],
        ),
        _market(
            "football",
            "plus_de_corners",
            "Équipe avec le plus de corners",
            "corners",
            [
                _sel("domicile", "Domicile"),
                _sel("exterieur", "Extérieur"),
                _sel("egalite", "Égalité"),
            ],
        ),
    ]

    # --- Marchés joueurs ----------------------------------------------------
    items += [
        _market(
            "football",
            "buteur",
            "Buteur",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
        _market(
            "football",
            "premier_buteur",
            "Premier buteur",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
        _market(
            "football",
            "dernier_buteur",
            "Dernier buteur",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
        _market(
            "football",
            "buteur_deux_buts",
            "Joueur marque au moins deux buts",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
        _market(
            "football",
            "buteur_trois_buts",
            "Joueur marque au moins trois buts",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
        _market(
            "football",
            "buteur_et_resultat",
            "Buteur et résultat",
            "joueur",
            [
                _sel("buteur_1", "Buteur / Domicile"),
                _sel("buteur_X", "Buteur / Nul"),
                _sel("buteur_2", "Buteur / Extérieur"),
            ],
            subject="player",
        ),
        _market(
            "football",
            "passeur_decisif",
            "Passeur décisif",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
        _market(
            "football",
            "buteur_ou_passeur",
            "Buteur ou passeur décisif",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
        _market(
            "football",
            "tirs_joueur",
            "Tirs du joueur",
            "joueur",
            OVER_UNDER,
            subject="player",
            line_kind="simple",
        ),
        _market(
            "football",
            "tirs_cadres_joueur",
            "Tirs cadrés du joueur",
            "joueur",
            OVER_UNDER,
            subject="player",
            line_kind="simple",
        ),
        _market(
            "football",
            "carton_joueur",
            "Le joueur reçoit un carton",
            "joueur",
            YES_NO,
            subject="player",
        ),
        _market(
            "football",
            "nombre_buts_joueur",
            "Nombre de buts du joueur",
            "joueur",
            [
                _sel("0", "0"),
                _sel("1", "1"),
                _sel("2", "2"),
                _sel("3_plus", "3 ou plus"),
            ],
            subject="player",
        ),
        _market(
            "football",
            "homme_du_match",
            "Homme du match",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
    ]

    # --- Combinés -----------------------------------------------------------
    items += [
        _market(
            "football",
            "resultat_et_total",
            "Résultat et total de buts",
            "combine",
            [
                _sel("1_plus", "Domicile / Plus"),
                _sel("1_moins", "Domicile / Moins"),
                _sel("X_plus", "Nul / Plus"),
                _sel("X_moins", "Nul / Moins"),
                _sel("2_plus", "Extérieur / Plus"),
                _sel("2_moins", "Extérieur / Moins"),
            ],
            line_kind="simple",
        ),
        _market(
            "football",
            "double_chance_et_total",
            "Double chance et total de buts",
            "combine",
            [
                _sel("1X_plus", "1X / Plus"),
                _sel("1X_moins", "1X / Moins"),
                _sel("12_plus", "12 / Plus"),
                _sel("12_moins", "12 / Moins"),
                _sel("X2_plus", "X2 / Plus"),
                _sel("X2_moins", "X2 / Moins"),
            ],
            line_kind="simple",
        ),
        _market(
            "football",
            "resultat_et_score_exact",
            "Résultat et score exact",
            "combine",
            [
                _sel("1_1_0", "Domicile / 1-0"),
                _sel("1_2_0", "Domicile / 2-0"),
                _sel("1_2_1", "Domicile / 2-1"),
                _sel("X_0_0", "Nul / 0-0"),
                _sel("X_1_1", "Nul / 1-1"),
                _sel("X_2_2", "Nul / 2-2"),
                _sel("2_0_1", "Extérieur / 0-1"),
                _sel("2_0_2", "Extérieur / 0-2"),
                _sel("2_1_2", "Extérieur / 1-2"),
            ],
        ),
        _market(
            "football",
            "total_et_btts",
            "Total de buts et les deux équipes marquent",
            "combine",
            [
                _sel("plus_oui", "Plus / Oui"),
                _sel("plus_non", "Plus / Non"),
                _sel("moins_oui", "Moins / Oui"),
                _sel("moins_non", "Moins / Non"),
            ],
            line_kind="simple",
        ),
        _market(
            "football",
            "resultat_double_chance",
            "Résultat ou double chance",
            "combine",
            [
                _sel("1_ou_1X", "Domicile ou 1X"),
                _sel("2_ou_X2", "Extérieur ou X2"),
                _sel("X_ou_1X", "Nul ou 1X"),
            ],
        ),
    ]

    return items


def _tennis_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "tennis",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2")],
        ),
        _market(
            "tennis",
            "vainqueur_set",
            "Vainqueur du 1er set",
            "resultat",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2")],
            period="set_1",
        ),
        _market(
            "tennis",
            "score_sets_exact",
            "Score exact en sets",
            "score_exact",
            [
                _sel("2_0", "2-0"),
                _sel("2_1", "2-1"),
                _sel("0_2", "0-2"),
                _sel("1_2", "1-2"),
                _sel("3_0", "3-0"),
                _sel("3_1", "3-1"),
                _sel("3_2", "3-2"),
                _sel("0_3", "0-3"),
                _sel("1_3", "1-3"),
                _sel("2_3", "2-3"),
            ],
        ),
        _market("tennis", "total_jeux", "Total de jeux", "totaux", OVER_UNDER, line_kind="simple"),
        _market("tennis", "total_sets", "Total de sets", "totaux", OVER_UNDER, line_kind="simple"),
        _market(
            "tennis", "handicap_jeux", "Handicap jeux", "handicap", HANDICAP, line_kind="simple"
        ),
        _market(
            "tennis", "handicap_sets", "Handicap sets", "handicap", HANDICAP, line_kind="simple"
        ),
        _market(
            "tennis", "total_aces", "Total d'aces", "statistiques", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "tennis",
            "total_doubles_fautes",
            "Total de doubles fautes",
            "statistiques",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market("tennis", "vainqueur_tie_break", "Un tie-break est joué", "statistiques", YES_NO),
        _market(
            "tennis",
            "jeu_decisif",
            "Vainqueur du jeu décisif",
            "resultat",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2")],
            period="tie_break",
        ),
        _market(
            "tennis",
            "premier_break",
            "Premier break du match",
            "statistiques",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2"), _sel("aucun", "Aucun")],
        ),
    ]


def _basketball_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "basketball",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
        ),
        _market("basketball", "handicap", "Handicap", "handicap", HANDICAP, line_kind="simple"),
        _market(
            "basketball",
            "total_points",
            "Total de points",
            "totaux",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "basketball",
            "total_points_equipe_domicile",
            "Total de points de l'équipe à domicile",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "basketball",
            "total_points_equipe_exterieur",
            "Total de points de l'équipe à l'extérieur",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "basketball",
            "vainqueur_1er_quart",
            "Vainqueur du 1er quart-temps",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
            period="quart_1",
        ),
        _market(
            "basketball",
            "vainqueur_mi_temps",
            "Vainqueur à la mi-temps",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
            period="mi_temps",
        ),
        _market(
            "basketball",
            "total_points_1er_quart",
            "Total de points du 1er quart-temps",
            "totaux",
            OVER_UNDER,
            period="quart_1",
            line_kind="simple",
        ),
        _market(
            "basketball",
            "ecart_final",
            "Écart final",
            "score_exact",
            [
                _sel("1_5", "1 à 5 points"),
                _sel("6_10", "6 à 10 points"),
                _sel("11_15", "11 à 15 points"),
                _sel("16_plus", "16 points ou plus"),
            ],
        ),
        _market(
            "basketball",
            "total_pairs_impairs",
            "Total de points pair / impair",
            "totaux",
            [_sel("pair", "Pair"), _sel("impair", "Impair")],
        ),
        _market(
            "basketball",
            "premier_a_10_points",
            "Première équipe à 10 points",
            "statistiques",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
        ),
        _market("basketball", "prolongation", "Prolongation", "statistiques", YES_NO),
    ]


def _hockey_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "hockey_sur_glace",
            "resultat_1x2",
            "Résultat (temps réglementaire)",
            "resultat",
            RESULT,
        ),
        _market(
            "hockey_sur_glace",
            "vainqueur",
            "Vainqueur du match (avec prolongation)",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
        ),
        _market(
            "hockey_sur_glace", "handicap", "Handicap", "handicap", HANDICAP, line_kind="simple"
        ),
        _market(
            "hockey_sur_glace",
            "total_buts",
            "Total de buts",
            "totaux",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "hockey_sur_glace",
            "total_buts_equipe",
            "Total de buts d'une équipe",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market("hockey_sur_glace", "btts", "Les deux équipes marquent", "btts", YES_NO),
        _market(
            "hockey_sur_glace",
            "resultat_1re_periode",
            "Résultat de la 1re période",
            "resultat",
            RESULT,
            period="periode_1",
        ),
        _market(
            "hockey_sur_glace",
            "total_buts_1re_periode",
            "Total de buts de la 1re période",
            "totaux",
            OVER_UNDER,
            period="periode_1",
            line_kind="simple",
        ),
        _market("hockey_sur_glace", "score_exact", "Score exact", "score_exact", EXACT_SCORE),
        _market("hockey_sur_glace", "prolongation", "Prolongation", "statistiques", YES_NO),
        _market(
            "hockey_sur_glace",
            "total_tirs",
            "Total de tirs",
            "statistiques",
            OVER_UNDER,
            line_kind="simple",
        ),
    ]


def _handball_catalog() -> list[MarketDefinition]:
    return [
        _market("handball", "resultat_1x2", "Résultat", "resultat", RESULT),
        _market("handball", "double_chance", "Double chance", "double_chance", DOUBLE_CHANCE),
        _market("handball", "handicap", "Handicap", "handicap", HANDICAP, line_kind="simple"),
        _market(
            "handball", "total_buts", "Total de buts", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "handball",
            "total_buts_equipe",
            "Total de buts d'une équipe",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "handball",
            "resultat_mi_temps",
            "Résultat à la mi-temps",
            "resultat",
            RESULT,
            period="mi_temps",
        ),
        _market(
            "handball",
            "total_buts_mi_temps",
            "Total de buts à la mi-temps",
            "totaux",
            OVER_UNDER,
            period="mi_temps",
            line_kind="simple",
        ),
        _market(
            "handball",
            "ecart_final",
            "Écart final",
            "score_exact",
            [
                _sel("0_3", "0 à 3 buts"),
                _sel("4_6", "4 à 6 buts"),
                _sel("7_10", "7 à 10 buts"),
                _sel("11_plus", "11 buts ou plus"),
            ],
        ),
        _market(
            "handball",
            "total_exclusions",
            "Total d'exclusions",
            "statistiques",
            OVER_UNDER,
            line_kind="simple",
        ),
    ]


def _rugby_catalog() -> list[MarketDefinition]:
    return [
        _market("rugby", "resultat_1x2", "Résultat", "resultat", RESULT),
        _market("rugby", "handicap", "Handicap", "handicap", HANDICAP, line_kind="simple"),
        _market(
            "rugby", "total_points", "Total de points", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "rugby", "total_essais", "Total d'essais", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "rugby",
            "total_points_equipe",
            "Total de points d'une équipe",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "rugby",
            "resultat_mi_temps",
            "Résultat à la mi-temps",
            "resultat",
            RESULT,
            period="mi_temps",
        ),
        _market(
            "rugby",
            "premier_essai",
            "Première équipe à marquer un essai",
            "statistiques",
            [_sel("1", "Domicile"), _sel("2", "Extérieur"), _sel("aucun", "Aucun")],
        ),
        _market(
            "rugby",
            "ecart_final",
            "Écart final",
            "score_exact",
            [
                _sel("0_7", "0 à 7 points"),
                _sel("8_14", "8 à 14 points"),
                _sel("15_21", "15 à 21 points"),
                _sel("22_plus", "22 points ou plus"),
            ],
        ),
    ]


def _volleyball_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "volleyball",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
        ),
        _market(
            "volleyball",
            "score_sets_exact",
            "Score exact en sets",
            "score_exact",
            [
                _sel("3_0", "3-0"),
                _sel("3_1", "3-1"),
                _sel("3_2", "3-2"),
                _sel("0_3", "0-3"),
                _sel("1_3", "1-3"),
                _sel("2_3", "2-3"),
            ],
        ),
        _market(
            "volleyball", "handicap_sets", "Handicap sets", "handicap", HANDICAP, line_kind="simple"
        ),
        _market(
            "volleyball", "total_sets", "Total de sets", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "volleyball",
            "total_points",
            "Total de points",
            "totaux",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "volleyball",
            "handicap_points",
            "Handicap points",
            "handicap",
            HANDICAP,
            line_kind="simple",
        ),
        _market(
            "volleyball",
            "vainqueur_1er_set",
            "Vainqueur du 1er set",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
            period="set_1",
        ),
        _market(
            "volleyball",
            "total_points_1er_set",
            "Total de points du 1er set",
            "totaux",
            OVER_UNDER,
            period="set_1",
            line_kind="simple",
        ),
    ]


def _baseball_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "baseball",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
        ),
        _market(
            "baseball", "run_line", "Handicap (run line)", "handicap", HANDICAP, line_kind="simple"
        ),
        _market(
            "baseball", "total_runs", "Total de points", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "baseball",
            "total_runs_equipe",
            "Total de points d'une équipe",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "baseball",
            "total_runs_1re_manche",
            "Total de points de la 1re manche",
            "totaux",
            OVER_UNDER,
            period="manche_1",
            line_kind="simple",
        ),
        _market(
            "baseball",
            "vainqueur_1re_manche",
            "Vainqueur de la 1re manche",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
            period="manche_1",
        ),
        _market("baseball", "btts", "Les deux équipes marquent", "btts", YES_NO),
        _market("baseball", "prolongation", "Prolongation", "statistiques", YES_NO),
    ]


def _american_football_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "football_americain",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
        ),
        _market(
            "football_americain",
            "spread",
            "Handicap (spread)",
            "handicap",
            HANDICAP,
            line_kind="simple",
        ),
        _market(
            "football_americain",
            "total_points",
            "Total de points",
            "totaux",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "football_americain",
            "total_points_equipe",
            "Total de points d'une équipe",
            "totaux",
            OVER_UNDER,
            subject="team",
            line_kind="simple",
        ),
        _market(
            "football_americain",
            "vainqueur_1er_quart",
            "Vainqueur du 1er quart-temps",
            "resultat",
            [_sel("1", "Domicile"), _sel("2", "Extérieur")],
            period="quart_1",
        ),
        _market(
            "football_americain",
            "total_touchdowns",
            "Total de touchdowns",
            "totaux",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market("football_americain", "prolongation", "Prolongation", "statistiques", YES_NO),
    ]


def _cricket_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "cricket",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Équipe 1"), _sel("2", "Équipe 2")],
        ),
        _market("cricket", "total_runs", "Total de runs", "totaux", OVER_UNDER, line_kind="simple"),
        _market(
            "cricket", "handicap_runs", "Handicap runs", "handicap", HANDICAP, line_kind="simple"
        ),
        _market(
            "cricket",
            "meilleur_batteur",
            "Meilleur batteur du match",
            "joueur",
            [_sel("oui", "Oui"), _sel("non", "Non")],
            subject="player",
        ),
        _market(
            "cricket",
            "total_guichets",
            "Total de guichets",
            "totaux",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "cricket",
            "vainqueur_toss",
            "Vainqueur du toss",
            "resultat",
            [_sel("1", "Équipe 1"), _sel("2", "Équipe 2")],
        ),
    ]


def _table_tennis_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "tennis_de_table",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2")],
        ),
        _market(
            "tennis_de_table",
            "score_sets_exact",
            "Score exact en sets",
            "score_exact",
            [
                _sel("3_0", "3-0"),
                _sel("3_1", "3-1"),
                _sel("3_2", "3-2"),
                _sel("0_3", "0-3"),
                _sel("1_3", "1-3"),
                _sel("2_3", "2-3"),
            ],
        ),
        _market(
            "tennis_de_table",
            "total_sets",
            "Total de sets",
            "totaux",
            OVER_UNDER,
            line_kind="simple",
        ),
        _market(
            "tennis_de_table",
            "handicap_sets",
            "Handicap sets",
            "handicap",
            HANDICAP,
            line_kind="simple",
        ),
        _market(
            "tennis_de_table",
            "total_points",
            "Total de points",
            "totaux",
            OVER_UNDER,
            line_kind="simple",
        ),
    ]


def _badminton_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "badminton",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2")],
        ),
        _market(
            "badminton",
            "score_sets_exact",
            "Score exact en sets",
            "score_exact",
            [
                _sel("2_0", "2-0"),
                _sel("2_1", "2-1"),
                _sel("0_2", "0-2"),
                _sel("1_2", "1-2"),
            ],
        ),
        _market(
            "badminton", "total_sets", "Total de sets", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "badminton", "total_points", "Total de points", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "badminton",
            "handicap_points",
            "Handicap points",
            "handicap",
            HANDICAP,
            line_kind="simple",
        ),
    ]


def _darts_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "darts",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2")],
        ),
        _market(
            "darts",
            "score_exact",
            "Score exact en légendes",
            "score_exact",
            [
                _sel("3_0", "3-0"),
                _sel("3_1", "3-1"),
                _sel("3_2", "3-2"),
                _sel("2_3", "2-3"),
                _sel("1_3", "1-3"),
                _sel("0_3", "0-3"),
            ],
        ),
        _market("darts", "total_180", "Total de 180", "totaux", OVER_UNDER, line_kind="simple"),
        _market(
            "darts", "handicap_legs", "Handicap légendes", "handicap", HANDICAP, line_kind="simple"
        ),
        _market(
            "darts",
            "plus_gros_checkout",
            "Plus gros checkout",
            "statistiques",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2")],
        ),
    ]


def _snooker_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "snooker",
            "vainqueur",
            "Vainqueur du match",
            "resultat",
            [_sel("1", "Joueur 1"), _sel("2", "Joueur 2")],
        ),
        _market(
            "snooker",
            "score_exact",
            "Score exact en frames",
            "score_exact",
            [
                _sel("4_0", "4-0"),
                _sel("4_1", "4-1"),
                _sel("4_2", "4-2"),
                _sel("4_3", "4-3"),
                _sel("3_4", "3-4"),
                _sel("2_4", "2-4"),
                _sel("1_4", "1-4"),
                _sel("0_4", "0-4"),
            ],
        ),
        _market(
            "snooker", "total_frames", "Total de frames", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "snooker",
            "handicap_frames",
            "Handicap frames",
            "handicap",
            HANDICAP,
            line_kind="simple",
        ),
        _market("snooker", "century_break", "Break de 100 points", "statistiques", YES_NO),
    ]


def _esport_catalog() -> list[MarketDefinition]:
    return [
        _market(
            "esport",
            "vainqueur_serie",
            "Vainqueur de la série",
            "resultat",
            [_sel("1", "Équipe 1"), _sel("2", "Équipe 2")],
        ),
        _market(
            "esport",
            "vainqueur_carte",
            "Vainqueur d'une carte",
            "resultat",
            [_sel("1", "Équipe 1"), _sel("2", "Équipe 2")],
            period="carte_1",
        ),
        _market(
            "esport",
            "score_cartes_exact",
            "Score exact en cartes",
            "score_exact",
            [
                _sel("2_0", "2-0"),
                _sel("2_1", "2-1"),
                _sel("0_2", "0-2"),
                _sel("1_2", "1-2"),
                _sel("3_0", "3-0"),
                _sel("3_1", "3-1"),
                _sel("3_2", "3-2"),
                _sel("0_3", "0-3"),
                _sel("1_3", "1-3"),
                _sel("2_3", "2-3"),
            ],
        ),
        _market(
            "esport", "total_cartes", "Total de cartes", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "esport", "handicap_cartes", "Handicap cartes", "handicap", HANDICAP, line_kind="simple"
        ),
        _market(
            "esport", "total_kills", "Total de kills", "totaux", OVER_UNDER, line_kind="simple"
        ),
        _market(
            "esport",
            "premier_sang",
            "Premier sang",
            "statistiques",
            [_sel("1", "Équipe 1"), _sel("2", "Équipe 2")],
        ),
    ]


MARKET_TEMPLATES: list[MarketDefinition] = [
    *_football_catalog(),
    *_tennis_catalog(),
    *_basketball_catalog(),
    *_hockey_catalog(),
    *_handball_catalog(),
    *_rugby_catalog(),
    *_volleyball_catalog(),
    *_baseball_catalog(),
    *_american_football_catalog(),
    *_cricket_catalog(),
    *_table_tennis_catalog(),
    *_badminton_catalog(),
    *_darts_catalog(),
    *_snooker_catalog(),
    *_esport_catalog(),
]
