"""Accounts and sessions.

Passwords are hashed with scrypt (stdlib). Sessions are opaque random tokens held in an
HttpOnly cookie; only their SHA-256 is stored, so a database leak does not leak sessions.
"""

import asyncio
import base64
import hashlib
import hmac
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, AuthSession, BootstrapLock, User

# scrypt cost: N=2**17 with r=8 needs ~128 MiB per hash (well under the 256 MiB maxmem cap we
# pass) and runs in ~0.9 s on commodity hardware. That blunts offline cracking of a leaked
# database. Existing hashes embed their own N/r/p, so old accounts keep verifying under the
# old cost until the next login/change; only newly written hashes use the stronger parameters.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**17, 8, 1
# OpenSSL's default 32 MiB cap would make N=2**17 fail outright; raise it explicitly.
SCRYPT_MAXMEM = 256 * 1024 * 1024
MIN_PASSWORD_LENGTH = 10
SESSION_COOKIE = "osint_session"

# scrypt is deliberately slow (~0.9 s); hashing on the event loop would stall every request
# for the whole process, so all hashing/verifying runs on this small dedicated pool.
_HASH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scrypt")


class AuthError(Exception):
    pass


class RegistrationClosed(AuthError):
    """Raised when an account already exists and open registration is disabled."""
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32,
                            maxmem=SCRYPT_MAXMEM)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


async def hash_password_async(password: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_HASH_POOL, hash_password, password)


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        # Derive maxmem from this hash's own n and r (128 bytes/element, doubled for OpenSSL's
        # bookkeeping headroom). Anything smaller makes OpenSSL raise "memory limit exceeded",
        # which would lock users out of legitimate hashes.
        maxmem = max(SCRYPT_MAXMEM, 128 * n * r * 2)
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=n, r=r, p=p,
                                dklen=len(expected), maxmem=maxmem)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


async def verify_password_async(password: str, stored: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_HASH_POOL, verify_password, password, stored)


# Burn equivalent time on unknown accounts so login timing doesn't reveal which emails exist.
# Built lazily off the event loop on first login (it costs ~0.9 s) and cached thereafter.
_DUMMY_HASH: str | None = None
_DUMMY_HASH_LOCK = asyncio.Lock()


async def _get_dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        async with _DUMMY_HASH_LOCK:
            if _DUMMY_HASH is None:
                _DUMMY_HASH = await hash_password_async(secrets.token_hex(8))
    return _DUMMY_HASH


def validate_password(password: str) -> str | None:
    """Return a user-facing message if the password is too weak, else None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.lower() == password and password.isalpha():
        return "Use a longer passphrase or mix in numbers or symbols."
    return None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def user_count(s: AsyncSession) -> int:
    return await s.scalar(select(func.count()).select_from(User)) or 0


async def create_user(s: AsyncSession, email: str, name: str, password: str, role: str) -> User:
    """Create a user outside the registration flow (admin-invited accounts). Raises AuthError on
    an invalid email, a weak password, or an address that's already taken."""
    email = normalize_email(email)
    if "@" not in email or len(email) > 320:
        raise AuthError("Enter a valid email address.")
    if await s.scalar(select(User.id).where(User.email == email)):
        raise AuthError("An account with this email already exists.")
    user = User(email=email, name=name.strip()[:128] or email.split("@")[0],
                password_hash=await hash_password_async(password), role=role)
    s.add(user)
    await s.flush()
    return user


async def register_user(s: AsyncSession, email: str, name: str, password: str, *,
                        allow_registration: bool) -> User | None:
    """Create the first account as admin, or a new account when open registration is allowed.

    Bootstrap is rare but must mint exactly one admin no matter how many requests race, so this
    serializes every registration on the singleton settings row: `INSERT ... ON CONFLICT DO
    NOTHING RETURNING` takes a write lock that concurrent requests queue behind (Postgres waits
    on the conflicting row lock; SQLite rejects the concurrent write). Each request therefore
    observes a fully-committed users table before choosing a role. Returns None if an account
    with that email already exists; raises AuthError if registration is closed.
    """
    email = normalize_email(email)
    if "@" not in email or len(email) > 320:
        raise AuthError("Enter a valid email address.")
    if (weak := validate_password(password)) is not None:
        raise AuthError(weak)

    dialect = s.get_bind().dialect.name
    upsert = sqlite.insert if dialect == "sqlite" else postgresql.insert
    lock = await s.execute(
        upsert(BootstrapLock)
        .values(key="bootstrap", allow_registration=allow_registration)
        .on_conflict_do_nothing(index_elements=["key"])
        .returning(BootstrapLock.key)
    )
    if lock.first() is None and not allow_registration:
        raise RegistrationClosed("Registration is closed. Ask an administrator for an account.")

    count = await user_count(s)             # now serialized under the write lock
    if await s.scalar(select(User.id).where(User.email == email)):
        return None                         # duplicate email
    return await create_user(s, email, name, password, "admin" if count == 0 else "analyst")


async def authenticate(s: AsyncSession, email: str, password: str) -> User:
    user = await s.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        await verify_password_async(password, await _get_dummy_hash())
        raise AuthError("Invalid email or password.")
    if not await verify_password_async(password, user.password_hash) or not user.is_active:
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
