from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.connection import SessionLocal
from app.database.models import PasswordResetToken, RefreshSession, User
from app.audit.service import record_event

bearer_scheme = HTTPBearer()

_auth_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_auth_rate_lock = threading.Lock()


def enforce_auth_rate_limit(request: Any, endpoint: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"{endpoint}:{client_ip}"
    now = time.monotonic()
    window_seconds = settings.auth_rate_limit_window_seconds

    with _auth_rate_lock:
        timestamps = _auth_rate_windows[key]
        while timestamps and timestamps[0] <= now - window_seconds:
            timestamps.popleft()
        if len(timestamps) >= settings.auth_rate_limit_requests:
            raise HTTPException(
                status_code=429,
                detail="Too many authentication requests. Try again later.",
            )
        timestamps.append(now)


def clear_auth_rate_limits() -> None:
    with _auth_rate_lock:
        _auth_rate_windows.clear()

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = password_hash.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iss": settings.token_issuer,
        "aud": settings.token_audience,
        "typ": "access",
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.access_token_expiry_seconds,
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded_payload = _b64url_encode(payload_json)
    signing_input = encoded_payload.encode("utf-8")
    signature = hmac.new(
        settings.app_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64url_encode(signature)}"


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_refresh_token(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    session = SessionLocal()
    try:
        session.add(
            RefreshSession(
                user_id=user_id,
                token_hash=_hash_refresh_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        session.commit()
        return token
    finally:
        session.close()


def rotate_refresh_token(token: str) -> tuple[User, str]:
    session = SessionLocal()
    try:
        refresh_session = (
            session.query(RefreshSession)
            .filter(RefreshSession.token_hash == _hash_refresh_token(token))
            .one_or_none()
        )
        now = datetime.now(timezone.utc)
        if (
            refresh_session is None
            or refresh_session.revoked_at is not None
            or refresh_session.expires_at <= now
        ):
            if refresh_session is not None and refresh_session.revoked_at is not None:
                session.query(RefreshSession).filter(
                    RefreshSession.user_id == refresh_session.user_id,
                    RefreshSession.revoked_at.is_(None),
                ).update(
                    {"revoked_at": now},
                    synchronize_session=False,
                )
                session.commit()
            raise HTTPException(status_code=401, detail="Refresh token is invalid.")

        user = session.get(User, refresh_session.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found.")

        new_token = secrets.token_urlsafe(48)
        replacement = RefreshSession(
            user_id=user.id,
            token_hash=_hash_refresh_token(new_token),
            expires_at=now + timedelta(days=30),
        )
        session.add(replacement)
        session.flush()
        refresh_session.revoked_at = now
        refresh_session.replaced_by_id = replacement.id
        session.commit()
        session.refresh(user)
        return user, new_token
    finally:
        session.close()


def revoke_refresh_token(
    token: str,
    request_id: str | None = None,
) -> bool:
    session = SessionLocal()
    try:
        refresh_session = (
            session.query(RefreshSession)
            .filter(RefreshSession.token_hash == _hash_refresh_token(token))
            .one_or_none()
        )
        if refresh_session is None or refresh_session.revoked_at is not None:
            return False
        refresh_session.revoked_at = datetime.now(timezone.utc)
        record_event(
            session,
            actor_user_id=refresh_session.user_id,
            action="auth.logout",
            resource_type="user",
            resource_id=str(refresh_session.user_id),
            outcome="success",
            request_id=request_id,
        )
        session.commit()
        return True
    finally:
        session.close()


def _hash_password_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_password_reset(
    email: str,
    request_id: str | None = None,
) -> str | None:
    session = SessionLocal()
    try:
        user = get_user_by_email(session, email.strip().lower())
        if user is None:
            record_event(
                session,
                actor_user_id=None,
                action="auth.password_reset_request",
                resource_type="user",
                resource_id=None,
                outcome="failure",
                request_id=request_id,
            )
            session.commit()
            return None

        now = datetime.now(timezone.utc)
        session.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        ).update({"expires_at": now}, synchronize_session=False)

        reset_token = secrets.token_urlsafe(48)
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_password_reset_token(reset_token),
                expires_at=now
                + timedelta(minutes=settings.password_reset_expiry_minutes),
            )
        )
        record_event(
            session,
            actor_user_id=user.id,
            action="auth.password_reset_request",
            resource_type="user",
            resource_id=str(user.id),
            outcome="success",
            request_id=request_id,
        )
        session.commit()
        return reset_token
    finally:
        session.close()


def reset_password(
    reset_token: str,
    new_password: str,
    request_id: str | None = None,
) -> bool:
    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        reset_record = (
            session.query(PasswordResetToken)
            .filter(
                PasswordResetToken.token_hash
                == _hash_password_reset_token(reset_token)
            )
            .one_or_none()
        )
        if (
            reset_record is None
            or reset_record.used_at is not None
            or reset_record.expires_at <= now
        ):
            record_event(
                session,
                actor_user_id=(
                    reset_record.user_id if reset_record is not None else None
                ),
                action="auth.password_reset",
                resource_type="user",
                resource_id=(
                    str(reset_record.user_id)
                    if reset_record is not None
                    else None
                ),
                outcome="failure",
                request_id=request_id,
            )
            session.commit()
            return False

        user = session.get(User, reset_record.user_id)
        if user is None:
            return False

        user.password_hash = hash_password(new_password)
        reset_record.used_at = now
        session.query(RefreshSession).filter(
            RefreshSession.user_id == user.id,
            RefreshSession.revoked_at.is_(None),
        ).update({"revoked_at": now}, synchronize_session=False)
        record_event(
            session,
            actor_user_id=user.id,
            action="auth.password_reset",
            resource_type="user",
            resource_id=str(user.id),
            outcome="success",
            request_id=request_id,
        )
        session.commit()
        return True
    finally:
        session.close()


def verify_token(token: str) -> dict[str, Any]:
    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token format.") from exc

    signing_input = payload_part.encode("utf-8")
    expected = _b64url_encode(
        hmac.new(
            settings.app_secret_key.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
    )

    if not hmac.compare_digest(signature_part, expected):
        raise HTTPException(status_code=401, detail="Token signature is invalid.")

    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Token payload is invalid.") from exc

    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="Token type is invalid.")

    if payload.get("iss") != settings.token_issuer:
        raise HTTPException(status_code=401, detail="Token issuer is invalid.")

    if payload.get("aud") != settings.token_audience:
        raise HTTPException(status_code=401, detail="Token audience is invalid.")

    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token has expired.")

    return payload


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.query(User).filter(User.email == email).one_or_none()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def register_user(
    email: str,
    username: str,
    password: str,
    role: str = "viewer",
    request_id: str | None = None,
) -> User:
    session = SessionLocal()
    try:
        email = email.strip().lower()
        username = username.strip()

        if not email or not username or not password:
            raise HTTPException(status_code=400, detail="Email, username, and password are required.")
        if get_user_by_email(session, email) is not None:
            raise HTTPException(status_code=409, detail="A user with this email already exists.")

        if role not in {"admin", "analyst", "viewer", "uploader"}:
            raise HTTPException(status_code=400, detail="Unsupported role.")

        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            role=role,
        )
        session.add(user)
        session.flush()
        record_event(
            session,
            actor_user_id=user.id,
            action="user.register",
            resource_type="user",
            resource_id=str(user.id),
            outcome="success",
            request_id=request_id,
        )
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def authenticate_user(
    email: str,
    password: str,
    request_id: str | None = None,
) -> User | None:
    session = SessionLocal()
    try:
        user = get_user_by_email(session, email.strip().lower())
        if user is None:
            record_event(
                session,
                actor_user_id=None,
                action="auth.login",
                resource_type="user",
                resource_id=None,
                outcome="failure",
                request_id=request_id,
            )
            session.commit()
            return None
        if not verify_password(password, user.password_hash):
            record_event(
                session,
                actor_user_id=user.id,
                action="auth.login",
                resource_type="user",
                resource_id=str(user.id),
                outcome="failure",
                request_id=request_id,
            )
            session.commit()
            return None
        record_event(
            session,
            actor_user_id=user.id,
            action="auth.login",
            resource_type="user",
            resource_id=str(user.id),
            outcome="success",
            request_id=request_id,
        )
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def get_current_user_from_token(token: str) -> User:
    payload = verify_token(token)
    session = SessionLocal()
    try:
        user = session.get(User, int(payload["sub"]))
        if user is None:
            raise HTTPException(status_code=401, detail="User not found.")
        return user
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> User:
    token = credentials.credentials
    return get_current_user_from_token(token)


def require_roles(*roles: str):
    def dependency(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    ):
        token = credentials.credentials
        user = get_current_user_from_token(token)

        if roles and user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )

        return user

    return dependency
