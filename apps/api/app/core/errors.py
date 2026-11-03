"""Gestion homogène des erreurs au format RFC 7807 (problem+json)."""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"

_TITLES: dict[int, str] = {
    400: "Requête invalide",
    401: "Authentification requise",
    403: "Accès refusé",
    404: "Ressource introuvable",
    409: "Conflit de données",
    422: "Données invalides",
    429: "Trop de tentatives",
    500: "Erreur interne",
}

# Traduction française des principaux codes d'erreur Pydantic.
_VALIDATION_MESSAGES: dict[str, str] = {
    "missing": "Ce champ est obligatoire.",
    "string_too_short": "Ce texte est trop court.",
    "string_too_long": "Ce texte est trop long.",
    "string_type": "Une valeur textuelle est attendue.",
    "int_parsing": "Un nombre entier est attendu.",
    "int_type": "Un nombre entier est attendu.",
    "float_parsing": "Un nombre est attendu.",
    "float_type": "Un nombre est attendu.",
    "bool_parsing": "Une valeur vrai/faux est attendue.",
    "bool_type": "Une valeur vrai/faux est attendue.",
    "uuid_parsing": "Identifiant invalide.",
    "uuid_type": "Identifiant invalide.",
    "datetime_parsing": "Date et heure invalides.",
    "datetime_from_date_parsing": "Date invalide.",
    "date_parsing": "Date invalide.",
    "date_from_datetime_parsing": "Date invalide.",
    "enum": "Valeur non autorisée.",
    "literal_error": "Valeur non autorisée.",
    "greater_than_equal": "La valeur est trop petite.",
    "less_than_equal": "La valeur est trop grande.",
    "greater_than": "La valeur est trop petite.",
    "less_than": "La valeur est trop grande.",
    "value_error": "Valeur invalide.",
}


def problem_response(
    status_code: int,
    detail: str,
    *,
    errors: list[dict[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "type": f"https://odds-analyst.local/erreurs/{status_code}",
        "title": _TITLES.get(status_code, "Erreur"),
        "status": status_code,
        "detail": detail,
    }
    if errors:
        payload["errors"] = errors
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload, media_type=PROBLEM_CONTENT_TYPE)


def _translate(location: list[Any], error_type: str, message: str) -> dict[str, Any]:
    field = ".".join(str(part) for part in location if part not in ("body", "query", "path"))
    if field == "email" and error_type == "value_error":
        text = "Adresse électronique invalide."
    elif error_type == "value_error":
        # Nos validateurs métier produisent déjà des messages en français.
        text = message.removeprefix("Value error, ") if message else "Valeur invalide."
    else:
        text = _VALIDATION_MESSAGES.get(error_type, "Valeur invalide.")
    return {"champ": field or "(corps de la requête)", "message": text}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            _translate(list(err["loc"]), err["type"], err.get("msg", ""))
            for err in exc.errors()
        ]
        return problem_response(
            422,
            "Certaines données saisies sont invalides.",
            errors=errors,
        )
