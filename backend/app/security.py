"""Authentication and role-based access control.

Passwords are PBKDF2-HMAC-SHA256 hashed (stdlib only; the SRS asks for
bcrypt cost >= 12 in production — noted as a divergence in ARCHITECTURE.md).
Login mints an opaque random bearer token stored in the auth_tokens table.

RBAC is enforced here at the API layer, not just hidden in the UI, per SRS
5.4: 'Authorisation is role-based access control ... enforced at the API
layer not just the user interface.'
"""

import hashlib
import os
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AuthToken, Role, User

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS)
    return secrets.compare_digest(digest.hex(), digest_hex)


def create_token(db: Session, user: User) -> str:
    token = secrets.token_hex(32)
    db.add(AuthToken(token=token, user_id=user.id))
    return token


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    row = db.scalar(select(AuthToken).where(AuthToken.token == auth.removeprefix("Bearer ")))
    if row is None or not row.user.active:
        raise HTTPException(401, "Invalid or expired token")
    return row.user


def require_roles(*roles: Role):
    """Dependency factory: allow only the given roles through."""

    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(r.value for r in roles)}")
        return user

    return checker


# Common role groups, named for readability at the router layer.
ANY_USER = Depends(current_user)
ADMIN_ONLY = Depends(require_roles(Role.admin))
THRESHOLD_MANAGERS = Depends(require_roles(Role.admin, Role.coordinator))
