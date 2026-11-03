"""Primitives de sécurité : hachage, jetons, sessions."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Paramètres Argon2id conformes aux recommandations OWASP (2024).
_hasher = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=2, hash_len=32, salt_len=16)

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    """Hache un mot de passe avec Argon2id."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Vérifie un mot de passe. Retourne False sans lever d'exception."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Indique si le hash doit être recalculé (paramètres obsolètes)."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def generate_token() -> str:
    """Génère un jeton opaque de 256 bits."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Empreinte SHA-256 d'un jeton, seule valeur stockée en base."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def password_policy_error(password: str) -> str | None:
    """Retourne un message d'erreur en français, ou None si le mot de passe est valide."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
    if password.isdigit():
        return "Le mot de passe ne peut pas être uniquement composé de chiffres."
    if len(set(password)) < 4:
        return "Le mot de passe est trop répétitif : utilisez des caractères variés."
    return None
