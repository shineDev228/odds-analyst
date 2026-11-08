"""Données de référence insérées au premier démarrage (idempotent)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.market_catalog import MARKET_TEMPLATES
from app.models.market import MarketTemplate
from app.models.reference import Sport
from app.models.settings import AppSetting

DEFAULT_SPORTS = [
    {"code": "football", "name": "Football"},
    {"code": "tennis", "name": "Tennis"},
    {"code": "basketball", "name": "Basketball"},
    {"code": "hockey_sur_glace", "name": "Hockey sur glace"},
    {"code": "handball", "name": "Handball"},
    {"code": "rugby", "name": "Rugby"},
    {"code": "volleyball", "name": "Volley-ball"},
    {"code": "baseball", "name": "Baseball"},
    {"code": "football_americain", "name": "Football américain"},
    {"code": "cricket", "name": "Cricket"},
    {"code": "tennis_de_table", "name": "Tennis de table"},
    {"code": "badminton", "name": "Badminton"},
    {"code": "darts", "name": "Fléchettes"},
    {"code": "snooker", "name": "Snooker"},
    {"code": "esport", "name": "Esport"},
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
    for sport_item in DEFAULT_SPORTS:
        exists = db.scalar(select(Sport).where(Sport.code == sport_item["code"]))
        if exists is None:
            db.add(Sport(**sport_item))

    for template_item in MARKET_TEMPLATES:
        template = db.scalar(
            select(MarketTemplate).where(MarketTemplate.code == template_item["code"])
        )
        if template is None:
            db.add(MarketTemplate(**template_item))
        else:
            # Le catalogue évolue avec le code : on rafraîchit les modèles.
            for field, field_value in template_item.items():
                setattr(template, field, field_value)

    for setting_key, setting_value in DEFAULT_SETTINGS.items():
        if db.get(AppSetting, setting_key) is None:
            db.add(AppSetting(key=setting_key, value=setting_value))

    db.commit()
