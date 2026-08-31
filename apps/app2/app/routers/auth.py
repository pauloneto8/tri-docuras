from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_ONBOARDING_KEY,
    create_user,
    get_user_by_email,
    login_user,
    logout_user,
    redirect_if_authenticated,
    require_user,
    sync_root_flag,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.models import User
from app.security.csrf import ensure_csrf_token, validate_csrf_token
from app.services.transaction_wizard import mark_login_prompt
from app.security.rate_limit import check_rate_limit
from app.services import finance
from app.timezone import local_today

router = APIRouter(tags=["auth"])


def get_templates(request: Request):
    return request.app.state.templates


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    redirect = redirect_if_authenticated(request, db)
    if redirect:
        return redirect
    templates = get_templates(request)
    info = None
    if request.query_params.get("pending") == "1":
        info = "Cadastro realizado. Aguarde a liberação do administrador para entrar."
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            "info": info,
            "allow_registration": settings.allow_registration,
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    try:
        check_rate_limit(request, key="login", limit=10, window_seconds=60)
    except HTTPException as exc:
        if exc.status_code == 429:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
                    "info": None,
                    "allow_registration": settings.allow_registration,
                },
                status_code=429,
            )
        raise
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "E-mail ou senha inválidos.",
                "info": None,
                "allow_registration": settings.allow_registration,
            },
            status_code=401,
        )
    sync_root_flag(user)
    db.commit()
    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Sua conta ainda não foi liberada pelo administrador.",
                "info": None,
                "allow_registration": settings.allow_registration,
            },
            status_code=403,
        )
    login_user(request, user)
    finance.seed_defaults(db, user.id)
    if not user.onboarding_completed:
        return RedirectResponse(url="/onboarding", status_code=303)
    mark_login_prompt(request.session)
    return RedirectResponse(url="/", status_code=303)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        return RedirectResponse(url="/login", status_code=303)
    redirect = redirect_if_authenticated(request, db)
    if redirect:
        return redirect
    templates = get_templates(request)
    return templates.TemplateResponse(
        "register.html", {"request": request, "error": None}
    )


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if not settings.allow_registration:
        return RedirectResponse(url="/login", status_code=303)
    templates = get_templates(request)
    try:
        check_rate_limit(request, key="register", limit=5, window_seconds=60)
    except HTTPException as exc:
        if exc.status_code == 429:
            return templates.TemplateResponse(
                "register.html",
                {
                    "request": request,
                    "error": "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
                },
                status_code=429,
            )
        raise
    if len(password) < 6:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "A senha deve ter pelo menos 6 caracteres."},
            status_code=400,
        )
    if get_user_by_email(db, email):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Este e-mail já está cadastrado."},
            status_code=400,
        )
    create_user(db, email=email, password=password, name=name)
    return RedirectResponse(url="/login?pending=1", status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    validate_csrf_token(request, csrf_token)
    logout_user(request)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(
    request: Request,
    user: User = Depends(require_user),
):
    if user.onboarding_completed:
        return RedirectResponse(url="/", status_code=303)
    templates = get_templates(request)
    return templates.TemplateResponse(
        "onboarding.html",
        {
            "request": request,
            "user": user,
            "error": None,
            "csrf_token": ensure_csrf_token(request),
            "today": local_today().isoformat(),
        },
    )


@router.post("/onboarding", response_class=HTMLResponse)
async def onboarding_submit(
    request: Request,
    name: str = Form(...),
    opening_balance: str = Form("0"),
    opening_balance_date: str = Form(""),
    csrf_token: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    validate_csrf_token(request, csrf_token)
    templates = get_templates(request)
    if user.onboarding_completed:
        return RedirectResponse(url="/", status_code=303)
    if len(name.strip()) < 2:
        return templates.TemplateResponse(
            "onboarding.html",
            {
                "request": request,
                "user": user,
                "error": "Informe um nome com pelo menos 2 caracteres.",
                "csrf_token": ensure_csrf_token(request),
                "today": local_today().isoformat(),
            },
            status_code=400,
        )
    balance_date = None
    if opening_balance_date.strip():
        try:
            balance_date = date.fromisoformat(opening_balance_date.strip())
        except ValueError:
            return templates.TemplateResponse(
                "onboarding.html",
                {
                    "request": request,
                    "user": user,
                    "error": "Data do saldo inicial inválida.",
                    "csrf_token": ensure_csrf_token(request),
                    "today": local_today().isoformat(),
                },
                status_code=400,
            )
    try:
        finance.complete_onboarding(
            db,
            user.id,
            name=name,
            opening_balance=opening_balance.strip() or "0",
            opening_balance_date=balance_date,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "onboarding.html",
            {
                "request": request,
                "user": user,
                "error": str(exc),
                "csrf_token": ensure_csrf_token(request),
                "today": local_today().isoformat(),
            },
            status_code=400,
        )
    request.session[SESSION_ONBOARDING_KEY] = True
    mark_login_prompt(request.session)
    return RedirectResponse(url="/", status_code=303)
