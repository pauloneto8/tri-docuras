import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import settings
from app.db import get_db
from app.models import User

SESSION_USER_ID_KEY = "user_id"
SESSION_ONBOARDING_KEY = "onboarding_completed"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower().strip()))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def sync_root_flag(user: User) -> None:
    user.is_root = user.email.lower() in settings.root_email_set
    if user.is_root:
        user.is_active = True


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    name: str,
    is_active: bool | None = None,
) -> User:
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        name=name.strip(),
    )
    sync_root_flag(user)
    if is_active is not None:
        user.is_active = is_active
    elif not user.is_root:
        user.is_active = False
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def read_scope_id(user: User) -> int:
    """Escopo pessoal: sempre os dados do usuário logado (inclusive root)."""
    return user.id


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not user_id:
        raise HTTPException(status_code=401, detail="Não autenticado")
    user = get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not user_id:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    user = get_user_by_id(db, user_id)
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_root(user: User = Depends(require_user)) -> User:
    if not user.is_root:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
    return user


def login_user(request: Request, user: User) -> None:
    request.session[SESSION_USER_ID_KEY] = user.id
    request.session[SESSION_ONBOARDING_KEY] = user.onboarding_completed


def logout_user(request: Request) -> None:
    request.session.clear()


def redirect_if_authenticated(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if user_id:
        user = get_user_by_id(db, user_id)
        if user and user.is_active:
            if not user.onboarding_completed:
                return RedirectResponse(url="/onboarding", status_code=303)
            return RedirectResponse(url="/", status_code=303)
    return None
