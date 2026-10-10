from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, csrf_protect, current_user, rate_limit_login, require_admin
from app.config import Settings, get_settings
from app.db import get_session
from app.models import AuditEvent, User
from app.services import auth

router = APIRouter(prefix="/api", dependencies=[Depends(csrf_protect)])


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AuthStatus(BaseModel):
    user: UserOut | None
    needs_setup: bool
    allow_registration: bool


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class RegisterIn(LoginIn):
    name: str = Field(default="", max_length=128)


class UserCreate(RegisterIn):
    role: Literal["admin", "analyst"] = "analyst"


class UserUpdate(BaseModel):
    role: Literal["admin", "analyst"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str | None
    action: str
    target: str | None
    ip: str | None
    at: datetime


def _set_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE, token, max_age=settings.session_ttl_hours * 3600, httponly=True,
        secure=settings.secure_cookies, samesite="lax", path="/",
    )


@router.get("/auth/status", response_model=AuthStatus)
async def auth_status(request: Request, session: AsyncSession = Depends(get_session),
                      settings: Settings = Depends(get_settings)) -> AuthStatus:
    user = await auth.user_for_token(session, request.cookies.get(auth.SESSION_COOKIE))
    return AuthStatus(user=UserOut.model_validate(user) if user else None,
                      needs_setup=await auth.user_count(session) == 0,
                      allow_registration=settings.allow_registration)


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit_login)])
async def register(body: RegisterIn, request: Request, response: Response,
                   session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    """The very first account becomes admin. Afterwards only if open registration is enabled."""
    if (weak := auth.validate_password(body.password)) is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, weak)
    try:
        user = await auth.register_user(session, body.email, body.name, body.password,
                                        allow_registration=settings.allow_registration)
    except auth.RegistrationClosed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except auth.AuthError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if user is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    token = await auth.create_session(session, user, settings.session_ttl_hours, client_ip(request))
    auth.audit(session, user, "user.register", user.email, client_ip(request))
    await session.commit()
    _set_cookie(response, token, settings)
    return user


@router.post("/auth/login", response_model=UserOut, dependencies=[Depends(rate_limit_login)])
async def login(body: LoginIn, request: Request, response: Response,
                session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    try:
        user = await auth.authenticate(session, body.email, body.password)
    except auth.AuthError as exc:
        auth.audit(session, None, "auth.login_failed", auth.normalize_email(body.email), client_ip(request))
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    token = await auth.create_session(session, user, settings.session_ttl_hours, client_ip(request))
    auth.audit(session, user, "auth.login", None, client_ip(request))
    await session.commit()
    _set_cookie(response, token, settings)
    return user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, session: AsyncSession = Depends(get_session)):
    await auth.revoke_session(session, request.cookies.get(auth.SESSION_COOKIE))
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChange, request: Request, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    if not await auth.verify_password_async(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect.")
    if (weak := auth.validate_password(body.new_password)) is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, weak)
    user.password_hash = await auth.hash_password_async(body.new_password)
    await auth.revoke_all_sessions(session, user.id)
    auth.audit(session, user, "user.password_changed", None, client_ip(request))
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@router.get("/users", response_model=list[UserOut])
async def list_users(_: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return (await session.scalars(select(User).order_by(User.created_at))).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, request: Request, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    try:
        user = await auth.create_user(session, body.email, body.name, body.password, body.role)
    except auth.AuthError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    auth.audit(session, admin, "user.create", user.email, client_ip(request))
    await session.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: UserUpdate, request: Request, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if user.id == admin.id and (body.role == "analyst" or body.is_active is False):
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't demote or deactivate your own account.")
    if body.role:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            await auth.revoke_all_sessions(session, user.id)
    if body.password:
        if (weak := auth.validate_password(body.password)) is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, weak)
        user.password_hash = await auth.hash_password_async(body.password)
        await auth.revoke_all_sessions(session, user.id)
    auth.audit(session, admin, "user.update", user.email, client_ip(request))
    await session.commit()
    return user


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(_: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return (await session.scalars(select(AuditEvent).order_by(AuditEvent.at.desc()).limit(500))).all()
