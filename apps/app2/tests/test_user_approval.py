import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import User
from app.services import admin


def test_new_user_is_inactive_by_default():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"pending_{suffix}@example.com",
        password="secret1",
        name="Pending",
    )
    try:
        assert user.is_active is False
        assert user.is_root is False
    finally:
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_admin_can_approve_user():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"approve_{suffix}@example.com",
        password="secret1",
        name="Approve Me",
    )
    try:
        assert user.is_active is False
        approved = admin.set_user_active(db, user.id, active=True)
        assert approved.is_active is True
        revoked = admin.set_user_active(db, user.id, active=False)
        assert revoked.is_active is False
    finally:
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_cannot_revoke_root_user():
    from app.config import settings

    import pytest
    from fastapi import HTTPException

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    root_email = f"root_revoke_{suffix}@example.com"
    settings.root_emails = root_email
    user = create_user(db, email=root_email, password="secret1", name="Root")
    try:
        assert user.is_active is True
        with pytest.raises(HTTPException) as exc:
            admin.set_user_active(db, user.id, active=False)
        assert exc.value.status_code == 400
    finally:
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
