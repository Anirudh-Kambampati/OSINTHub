"""Accounts and sessions.

Passwords are hashed with scrypt (stdlib). Sessions are opaque random tokens held in an
HttpOnly cookie; only their SHA-256 is stored, so a database leak does not leak sessions.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, AuthSession, User

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MIN_PASSWORD_LENGTH = 10
SESSION_COOKIE = "osint_session"


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Burn equivalent time on unknown accounts so login timing doesn't reveal which emails exist.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password.lower() == password and password.isalpha():
        raise AuthError("Use a longer passphrase or mix in numbers or symbols.")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def user_count(s: AsyncSession) -> int:
    return await s.scalar(select(func.count()).select_from(User)) or 0


async def create_user(s: AsyncSession, email: str, name: str, password: str, role: str) -> User:
    email = normalize_email(email)
    if "@" not in email or len(email) > 320:
        raise AuthError("Enter a valid email address.")
    validate_password(password)
    if await s.scalar(select(User.id).where(User.email == email)):
        raise AuthError("An account with this email already exists.")
    user = User(email=email, name=name.strip()[:128] or email.split("@")[0], password_hash=hash_password(password),
                role=role)
    s.add(user)
    await s.flush()
    return user


async def authenticate(s: AsyncSession, email: str, password: str) -> User:
    user = await s.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise AuthError("Invalid email or password.")
    if not verify_password(password, user.password_hash) or not user.is_active:
        raise AuthError("Invalid email or password.")
    user.last_login_at = datetime.now(UTC)
    return user


async def create_session(s: AsyncSession, user: User, ttl_hours: int, ip: str | None) -> str:
    token = secrets.token_urlsafe(32)
    s.add(AuthSession(token_hash=token_hash(token), user_id=user.id, ip=ip,
                      expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours)))
    await s.execute(delete(AuthSession).where(AuthSession.expires_at < datetime.now(UTC)))
    return token


async def user_for_token(s: AsyncSession, token: str | None) -> User | None:
    if not token:
        return None
    row = await s.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    if row is None or row.expires_at < datetime.now(UTC):
        return None
    user = await s.get(User, row.user_id)
    return user if user and user.is_active else None


async def revoke_session(s: AsyncSession, token: str | None) -> None:
    if token:
        await s.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))


async def revoke_all_sessions(s: AsyncSession, user_id: str) -> None:
    await s.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


def audit(s: AsyncSession, user: User | None, action: str, target: str | None = None, ip: str | None = None) -> None:
    s.add(AuditEvent(user_id=user.id if user else None, action=action, target=(target or "")[:512] or None, ip=ip))
