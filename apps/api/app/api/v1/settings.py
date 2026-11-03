"""Paramètres applicatifs."""

from fastapi import APIRouter, Depends

from app.core import deps
from app.db.seed import DEFAULT_SETTINGS
from app.models.settings import AppSetting
from app.schemas.settings import PreferencesRead, PreferencesUpdate
from app.services import audit

router = APIRouter(
    prefix="/settings",
    tags=["Paramètres"],
    dependencies=[Depends(deps.get_auth_context), Depends(deps.verify_csrf)],
)

_KEY = "preferences"


@router.get("", response_model=PreferencesRead, summary="Lire les préférences")
def get_settings(db: deps.DbSession) -> PreferencesRead:
    row = db.get(AppSetting, _KEY)
    data = row.value if row and isinstance(row.value, dict) else DEFAULT_SETTINGS[_KEY]
    return PreferencesRead.model_validate({**DEFAULT_SETTINGS[_KEY], **data})


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
    audit.record(db, "settings.update", user_id=user.id, entity="settings", entity_id=_KEY,
                 payload=data)
    return PreferencesRead.model_validate(data)
