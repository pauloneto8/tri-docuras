import secrets

from fastapi import HTTPException, Request

CSRF_SESSION_KEY = "csrf_token"


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(request: Request, token: str | None) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)
    if not expected or not token or not secrets.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")
