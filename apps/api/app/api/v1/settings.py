"""Paramètres applicatifs."""

from fastapi import APIRouter, Depends

from app.core import deps
from app.models.settings import AppSetting
from app.schemas.settings import PreferencesRead, PreferencesUpdate
from app.services import audit
from app.services.preferences import PREFERENCES_KEY, get_preferences

router = APIRouter(
    prefix="/settings",
    tags=["Paramètres"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)

_KEY = PREFERENCES_KEY


@router.get("", response_model=PreferencesRead, summary="Lire les préférences")
def get_settings(db: deps.DbSession) -> PreferencesRead:
    return get_preferences(db)


@router.put("", response_model=PreferencesRead, summary="Enregistrer les préférences")
def update_settings(
    payload: PreferencesUpdate, db: deps.DbSession, user: deps.CurrentUser
) -> PreferencesRead:
    data = payload.model_dump()
    row = db.get(AppSetting, _KEY)
    if row is None:
        db.add(AppSetting(key=_KEY, value=data))
    else:
        row.value = data
    db.commit()
    audit.record(
        db,
        "settings.update",
        user_id=user.id,
        entity="settings",
        entity_id=_KEY,
        payload=data,
    )
    return PreferencesRead.model_validate(data)
