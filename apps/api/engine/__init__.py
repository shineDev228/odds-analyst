"""Moteur statistique de ODDS ANALYST.

Ce paquet est volontairement PUR :
- aucun import de SQLAlchemy, FastAPI, requests ou httpx ;
- aucune lecture de fichier ni accès réseau ;
- uniquement des fonctions déterministes, testables isolément.

Cette contrainte garantit la reproductibilité des calculs et permet de
valider le moteur indépendamment de l'application.

Sous-modules prévus :
    ratings/       forces d'attaque et de défense
    models/        Poisson, Dixon-Coles
    markets/       dérivation des marchés depuis la matrice de scores
    uncertainty/   bootstrap, intervalles, qualité des données
    combos/        générateur de combinaisons
"""

__version__ = "1.0.0"
