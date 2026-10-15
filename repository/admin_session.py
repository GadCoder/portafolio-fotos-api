import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from db.models.admin_session import AdminSession


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_active_admin_session(
    db: Session, token: str | None, *, now: datetime | None = None
) -> AdminSession | None:
    if not token:
        return None

    session = (
        db.query(AdminSession)
        .filter(AdminSession.token_hash == _token_digest(token))
        .first()
    )
    if session is None:
        return None

    current_time = now or datetime.now(timezone.utc)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= current_time:
        db.delete(session)
        db.commit()
        return None
    return session


def create_admin_session(
    db: Session,
    user: str,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> tuple[str, AdminSession]:
    current_time = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(48)
    session = AdminSession(
        token_hash=_token_digest(token),
        user=user,
        csrf_token=secrets.token_urlsafe(32),
        created_at=current_time,
        expires_at=current_time + timedelta(seconds=max_age_seconds),
    )
    db.query(AdminSession).filter(AdminSession.user == user).delete(
        synchronize_session="fetch"
    )
    db.add(session)
    db.commit()
    return token, session


def revoke_admin_session(db: Session, session: AdminSession) -> None:
    db.delete(session)
    db.commit()
