from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.chat_format import chat_md
from app.config import settings
from app.routers import api, auth, pages
from app.security.csrf import ensure_csrf_token
from app.timezone import to_local_datetime

PUBLIC_PATHS = {"/login", "/register", "/api/health"}
ONBOARDING_EXEMPT = {"/onboarding", "/logout"}

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="AssistFin",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)

app.state.templates = Jinja2Templates(directory=str(templates_dir))
app.state.templates.env.filters["local_datetime"] = (
    lambda value, fmt="%d/%m/%Y %H:%M": ""
    if value is None
    else to_local_datetime(value).strftime(fmt)
)
app.state.templates.env.filters["chat_md"] = chat_md
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.middleware("http")
async def ensure_csrf_middleware(request: Request, call_next):
    if request.session.get("user_id"):
        ensure_csrf_token(request)
    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


@app.middleware("http")
async def onboarding_redirect_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in PUBLIC_PATHS or path in ONBOARDING_EXEMPT:
        return await call_next(request)
    if request.session.get("user_id") and not request.session.get("onboarding_completed"):
        if path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Conclua o cadastro inicial da sua conta principal."},
                status_code=403,
            )
        return RedirectResponse(url="/onboarding", status_code=303)
    return await call_next(request)


@app.middleware("http")
async def auth_redirect_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in PUBLIC_PATHS:
        return await call_next(request)
    if request.session.get("user_id"):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Não autenticado"}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="financas_session",
    max_age=60 * 60 * 24 * 7,
    https_only=False,
    same_site="lax",
)

if settings.trusted_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(api.router)
