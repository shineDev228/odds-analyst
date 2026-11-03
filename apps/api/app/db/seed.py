"""Données de référence insérées au premier démarrage (idempotent)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reference import Sport
from app.models.settings import AppSetting

DEFAULT_SPORTS = [
    {"code": "football", "name": "Football"},
]

DEFAULT_SETTINGS = {
    "preferences": {
        "cote_min": 50.0,
        "cote_max": 100.0,
        "nb_selections_defaut": 8,
        "marches_autorises": ["1X2", "DOUBLE_CHANCE", "PLUS_MOINS"],
        "demi_vie_jours": 240,
        "nb_matchs_historique": 38,
    }
}


def seed_defaults(db: Session) -> None:
    for item in DEFAULT_SPORTS:
        exists = db.scalar(select(Sport).where(Sport.code == item["code"]))
        if exists is None:
            db.add(Sport(**item))

    for key, value in DEFAULT_SETTINGS.items():
        if db.get(AppSetting, key) is None:
            db.add(AppSetting(key=key, value=value))

    db.commit()
