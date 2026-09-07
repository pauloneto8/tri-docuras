from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.runner import process_message
from app.auth import read_scope_id, require_root, require_user
from app.db import get_db
from app.models import Account, Category, CreditCard, User
from app.security.csrf import ensure_csrf_token, validate_csrf_token
from app.schemas import (
    BudgetCreate,
    BudgetStatusInput,
    CreateAccountInput,
    CreateCardInput,
    DeleteCardInput,
    DeleteTransactionInput,
    ListTransactionsInput,
    RealizePlannedInput,
    SummaryInput,
    ToolCall,
    TransactionCreate,
    UpdateAccountInput,
    UpdateCardInput,
    UpdateTransactionInput,
    UpdateTransferInput,
    decimal_to_cents,
)
from app.services import admin, finance
from app.services import ofx_card_import
from app.services import ofx_account_import
from app.timezone import local_today
from app.services.conversations import get_or_create_conversation, log_message
from app.services.transaction_wizard import (
    begin_login_prompt,
    clear_wizard as clear_transaction_wizard,
    consume_login_prompt,
    get_wizard as get_transaction_wizard,
)
from app.services.tools import execute_tool, format_tool_result

router = APIRouter(dependencies=[Depends(require_user)])


def get_templates(request: Request):
    return request.app.state.templates


def _form_optional_int(value: str | int | None) -> int | None:
    """HTML <select> envia '' quando sem opção — não dá para tipar como int | None direto."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text)


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    period: str = "month",
    ref_date: str | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    scope = read_scope_id(user)
    finance.seed_defaults(db, user.id)
    from app.services.recurrence import ensure_recurring_horizon

    ensure_recurring_horizon(db, scope)

    if period not in {"day", "week", "month"}:
        period = "month"
    try:
        current_ref = date.fromisoformat(ref_date) if ref_date else local_today()
    except ValueError:
        current_ref = local_today()

    summary = finance.get_summary(
        db,
        scope,
        SummaryInput(period=period, ref_date=current_ref),
    )
    period_end = date.fromisoformat(summary["period_end"])
    period_start = date.fromisoformat(summary["period_start"])
    balances = finance.account_balances(db, scope, as_of=period_end)
    recent = [
        tx
        for tx in finance.list_transactions(
            db,
            scope,
            ListTransactionsInput(
                limit=10,
                status="actual",
                start_date=period_start,
                end_date=period_end,
            ),
        )
        if not tx.get("card")
    ]
    budgets = finance.get_budget_status(
        db, scope, BudgetStatusInput(year=summary["year"], month=summary["month"])
    )
    prev_ref = finance.shift_ref_date(period, current_ref, -1)
    next_ref = finance.shift_ref_date(period, current_ref, 1)
    show_agent_welcome = request.session.get("prompt_transaction_on_login", False)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "is_root": user.is_root,
            "summary": summary,
            "balances": balances,
            "recent": recent,
            "budgets": budgets,
            "today": local_today(),
            "show_agent_welcome": show_agent_welcome,
            "period": period,
            "ref_date": current_ref.isoformat(),
            "prev_ref_date": prev_ref.isoformat(),
            "next_ref_date": next_ref.isoformat(),
        },
    )


def _parse_transactions_period(
    period: str | None,
    ref_date: str | None,
) -> tuple[str, date, date, date, str]:
    """Retorna period, current_ref, period_start, period_end, period_label."""
    if period not in {"day", "week", "month"}:
        period = "month"
    try:
        current_ref = date.fromisoformat(ref_date) if ref_date else local_today()
    except ValueError:
        current_ref = local_today()
    period_start, period_end = finance.resolve_period_bounds(period, current_ref)
    period_label = finance.format_period_label(period, period_start, period_end)
    return period, current_ref, period_start, period_end, period_label


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


_TX_FILTER_SESSION_KEY = "transactions_list_filter"


def _tx_filter_defaults() -> dict:
    return {
        "period": "month",
        "ref_date": None,
        "account_id": None,
        "card_id": None,
        "category_id": None,
        "type": "all",
    }


def _normalize_tx_filter_type(raw: str | None) -> str:
    value = (raw or "all").strip().lower()
    if value not in {"expense", "income", "transfer", "all"}:
        return "all"
    return value


def _read_saved_tx_filters(session: dict) -> dict:
    saved = session.get(_TX_FILTER_SESSION_KEY)
    if not isinstance(saved, dict):
        return _tx_filter_defaults()
    defaults = _tx_filter_defaults()
    return {
        "period": saved.get("period") or defaults["period"],
        "ref_date": saved.get("ref_date"),
        "account_id": saved.get("account_id"),
        "card_id": saved.get("card_id"),
        "category_id": saved.get("category_id"),
        "type": _normalize_tx_filter_type(saved.get("type")),
    }


def _write_tx_filters(session: dict, filters: dict) -> None:
    session[_TX_FILTER_SESSION_KEY] = {
        "period": filters.get("period") or "month",
        "ref_date": filters.get("ref_date"),
        "account_id": filters.get("account_id"),
        "card_id": filters.get("card_id"),
        "category_id": filters.get("category_id"),
        "type": _normalize_tx_filter_type(filters.get("type")),
    }


def _resolve_transactions_filters(request: Request) -> dict:
    """Resolve filtros da query + sessão. Sem query → restaura sessão; clear=1 → padrão."""
    qp = request.query_params
    clear = (qp.get("clear") or "").strip().lower() in {"1", "true", "yes"}
    if clear:
        request.session.pop(_TX_FILTER_SESSION_KEY, None)
        return _tx_filter_defaults()

    saved = _read_saved_tx_filters(request.session)
    if len(qp) == 0:
        return saved

    resolved = dict(saved)
    if "period" in qp:
        resolved["period"] = (qp.get("period") or "month").strip().lower() or "month"
    if "ref_date" in qp:
        raw_ref = (qp.get("ref_date") or "").strip()
        resolved["ref_date"] = raw_ref or None
    if "account_id" in qp:
        resolved["account_id"] = _parse_optional_int(qp.get("account_id"))
    if "card_id" in qp:
        resolved["card_id"] = _parse_optional_int(qp.get("card_id"))
    if "category_id" in qp:
        resolved["category_id"] = _parse_optional_int(qp.get("category_id"))
    if "type" in qp:
        resolved["type"] = _normalize_tx_filter_type(qp.get("type"))

    _write_tx_filters(request.session, resolved)
    return resolved


def _transactions_filter_suffix(
    *,
    account_id: int | None = None,
    card_id: int | None = None,
    category_id: int | None = None,
    tx_type: str = "all",
) -> str:
    from urllib.parse import urlencode

    params: dict[str, str] = {}
    if account_id is not None:
        params["account_id"] = str(account_id)
    if card_id is not None:
        params["card_id"] = str(card_id)
    if category_id is not None:
        params["category_id"] = str(category_id)
    if tx_type and tx_type != "all":
        params["type"] = tx_type
    if not params:
        return ""
    return "&" + urlencode(params)


def _transactions_filter_query(
    *,
    period: str,
    ref_date: str,
    account_id: int | None = None,
    card_id: int | None = None,
    category_id: int | None = None,
    tx_type: str = "all",
) -> str:
    from urllib.parse import urlencode

    params: dict[str, str] = {"period": period, "ref_date": ref_date}
    if account_id is not None:
        params["account_id"] = str(account_id)
    if card_id is not None:
        params["card_id"] = str(card_id)
    if category_id is not None:
        params["category_id"] = str(category_id)
    if tx_type and tx_type != "all":
        params["type"] = tx_type
    return urlencode(params)


def _transactions_page_context(
    request: Request,
    user: User,
    db: Session,
    *,
    success: str | None = None,
    error: str | None = None,
    period: str | None = None,
    ref_date: str | None = None,
    account_id: int | None = None,
    card_id: int | None = None,
    category_id: int | None = None,
    tx_type: str | None = None,
) -> dict:
    scope = read_scope_id(user)
    finance.seed_defaults(db, user.id)
    from app.services.recurrence import ensure_recurring_horizon
    from app.services.credit_cards import list_credit_cards

    ensure_recurring_horizon(db, scope)

    filters = _resolve_transactions_filters(request)
    # Argumentos explícitos (ex.: após POST com erro) sobrescrevem a resolução
    if period is not None:
        filters["period"] = period
    if ref_date is not None:
        filters["ref_date"] = ref_date
    if account_id is not None:
        filters["account_id"] = account_id
    if card_id is not None:
        filters["card_id"] = card_id
    if category_id is not None:
        filters["category_id"] = category_id
    if tx_type is not None:
        filters["type"] = _normalize_tx_filter_type(tx_type)

    period, current_ref, period_start, period_end, period_label = (
        _parse_transactions_period(filters.get("period"), filters.get("ref_date"))
    )
    prev_ref = finance.shift_ref_date(period, current_ref, -1)
    next_ref = finance.shift_ref_date(period, current_ref, 1)

    account_id = filters.get("account_id")
    card_id = filters.get("card_id")
    category_id = filters.get("category_id")
    tx_type = _normalize_tx_filter_type(filters.get("type"))

    # Validar filtros contra o usuário
    if account_id is not None:
        account = finance.find_account(db, user.id, account_id=account_id)
        if account is None:
            account_id = None
    if card_id is not None:
        card = finance.find_card(db, user.id, card_id=card_id)
        if card is None:
            card_id = None
    if category_id is not None:
        category = db.get(Category, category_id)
        if category is None or category.user_id != user.id:
            category_id = None

    # Persistir período resolvido (ref_date canônica) junto com filtros válidos
    if (request.query_params.get("clear") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        _write_tx_filters(
            request.session,
            {
                "period": period,
                "ref_date": current_ref.isoformat(),
                "account_id": account_id,
                "card_id": card_id,
                "category_id": category_id,
                "type": tx_type,
            },
        )

    list_filter: dict = dict(
        limit=100,
        start_date=period_start,
        end_date=period_end,
        type=tx_type,
    )
    if account_id is not None:
        list_filter["account_id"] = account_id
    if card_id is not None:
        list_filter["card_id"] = card_id
    if category_id is not None:
        list_filter["category_id"] = category_id

    planned = finance.list_transactions(
        db, scope, ListTransactionsInput(status="planned", **list_filter)
    )
    pending_transactions = [tx for tx in planned if not tx["is_realized"]]
    actual_raw = finance.list_transactions(
        db, scope, ListTransactionsInput(status="actual", **list_filter)
    )
    actual_transactions = []
    for tx in actual_raw:
        if tx.get("type") == "transfer_in":
            continue
        # Extrato padrão omite compras de cartão; com filtro de cartão, mostra.
        if card_id is None and tx.get("card"):
            continue
        actual_transactions.append(tx)

    flash_success = request.session.pop("flash_success", None)
    flash_error = request.session.pop("flash_error", None)
    accounts = (
        db.query(Account)
        .filter(
            Account.user_id == user.id,
            Account.is_active.is_(True),
            Account.account_type != "cartao",
        )
        .order_by(Account.name)
        .all()
    )
    credit_cards = list_credit_cards(db, user.id)
    categories = finance.list_user_categories(db, user.id)
    filter_qs = _transactions_filter_query(
        period=period,
        ref_date=current_ref.isoformat(),
        account_id=account_id,
        card_id=card_id,
        category_id=category_id,
        tx_type=tx_type,
    )
    filter_suffix = _transactions_filter_suffix(
        account_id=account_id,
        card_id=card_id,
        category_id=category_id,
        tx_type=tx_type,
    )
    filter_active = any(
        [
            account_id is not None,
            card_id is not None,
            category_id is not None,
            tx_type != "all",
        ]
    )
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "pending_transactions": pending_transactions,
        "actual_transactions": actual_transactions,
        "accounts": accounts,
        "credit_cards": credit_cards,
        "categories": categories,
        "filter_account_id": account_id,
        "filter_card_id": card_id,
        "filter_category_id": category_id,
        "filter_type": tx_type,
        "filter_qs": filter_qs,
        "filter_suffix": filter_suffix,
        "filter_active": filter_active,
        "success": success or flash_success,
        "error": error or flash_error,
        "today": local_today().isoformat(),
        "period": period,
        "ref_date": current_ref.isoformat(),
        "period_label": period_label,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "prev_ref_date": prev_ref.isoformat(),
        "next_ref_date": next_ref.isoformat(),
    }


def _transaction_form_context(
    request: Request,
    user: User,
    db: Session,
    *,
    success: str | None = None,
    error: str | None = None,
    tx: dict | None = None,
) -> dict:
    finance.seed_defaults(db, user.id)
    categories = (
        db.query(Category)
        .filter(Category.user_id == user.id)
        .order_by(Category.name)
        .all()
    )
    accounts = (
        db.query(Account)
        .filter(
            Account.user_id == user.id,
            Account.is_active.is_(True),
            Account.account_type != "cartao",
        )
        .order_by(Account.name)
        .all()
    )
    from app.services.credit_cards import list_credit_cards

    credit_cards = list_credit_cards(db, user.id)
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "categories": categories,
        "accounts": accounts,
        "credit_cards": credit_cards,
        "success": success,
        "error": error,
        "today": local_today().isoformat(),
        "tx": tx,
    }


def _flash_and_redirect(
    request: Request,
    url: str,
    *,
    success: str | None = None,
    error: str | None = None,
):
    if success:
        request.session["flash_success"] = success
    if error:
        request.session["flash_error"] = error
    return RedirectResponse(url=url, status_code=303)


def _flash_and_redirect_transactions(request: Request, *, success: str | None = None, error: str | None = None):
    return _flash_and_redirect(request, "/transactions", success=success, error=error)


def _consume_flash(request: Request, *, success: str | None = None, error: str | None = None):
    return (
        success or request.session.pop("flash_success", None),
        error or request.session.pop("flash_error", None),
    )


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    # Limpar filtros → padrão (mês atual) e remove da sessão
    if (request.query_params.get("clear") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        request.session.pop(_TX_FILTER_SESSION_KEY, None)
        return RedirectResponse(url="/transactions", status_code=303)

    templates = get_templates(request)
    return templates.TemplateResponse(
        "transactions.html",
        _transactions_page_context(request, user, db),
    )


@router.get("/transactions/new", response_class=HTMLResponse)
async def transaction_new_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    return templates.TemplateResponse(
        "transaction_form.html",
        _transaction_form_context(request, user, db),
    )


def _build_accounts_context(
    request: Request,
    user: User,
    db: Session,
    scope: int | None,
    *,
    focus_cards: bool = False,
    success: str | None = None,
    error: str | None = None,
    **extra,
):
    from app.services.credit_cards import (
        cards_with_nested_invoices,
        list_credit_cards,
        list_invoices,
        sync_credit_cards,
    )

    finance.seed_defaults(db, user.id)
    sync_credit_cards(db, user.id)
    bank_accounts = finance.account_balances(db, scope)
    credit_cards = list_credit_cards(db, user.id)
    invoices = list_invoices(db, user.id, limit=20)
    cards_tree = cards_with_nested_invoices(db, user.id) if focus_cards else []
    flash_success, flash_error = _consume_flash(request, success=success, error=error)
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "accounts": cards_tree if focus_cards else bank_accounts,
        "all_accounts": bank_accounts,
        "credit_cards": credit_cards,
        "bank_accounts": bank_accounts,
        "invoices": invoices,
        "debit_accounts": bank_accounts,
        "focus_cards": focus_cards,
        "today": local_today().isoformat(),
        "success": flash_success,
        "error": flash_error,
        **extra,
    }


def _account_form_context(
    request: Request,
    user: User,
    db: Session,
    *,
    account: dict | None = None,
    success: str | None = None,
    error: str | None = None,
) -> dict:
    finance.seed_defaults(db, user.id)
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "account": account,
        "today": local_today().isoformat(),
        "success": success,
        "error": error,
    }


def _card_form_context(
    request: Request,
    user: User,
    db: Session,
    *,
    card: dict | None = None,
    success: str | None = None,
    error: str | None = None,
) -> dict:
    scope = read_scope_id(user)
    finance.seed_defaults(db, user.id)
    bank_accounts = finance.account_balances(db, scope)
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "card": card,
        "bank_accounts": bank_accounts,
        "today": local_today().isoformat(),
        "success": success,
        "error": error,
    }


@router.get("/accounts", response_class=HTMLResponse)
async def accounts_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    scope = read_scope_id(user)
    return templates.TemplateResponse(
        "accounts.html",
        _build_accounts_context(request, user, db, scope),
    )


@router.get("/accounts/new", response_class=HTMLResponse)
async def account_new_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    return templates.TemplateResponse(
        "account_form.html",
        _account_form_context(request, user, db),
    )


@router.get("/accounts/cards", response_class=HTMLResponse)
async def cards_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    scope = read_scope_id(user)
    return templates.TemplateResponse(
        "accounts.html",
        _build_accounts_context(request, user, db, scope, focus_cards=True),
    )


@router.get("/accounts/cards/new", response_class=HTMLResponse)
async def card_new_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    return templates.TemplateResponse(
        "card_form.html",
        _card_form_context(request, user, db),
    )


@router.post("/accounts", response_class=HTMLResponse)
async def create_account_form(
    request: Request,
    name: str = Form(...),
    account_type: str = Form(...),
    institution: str = Form(""),
    opening_balance: str = Form(""),
    opening_balance_date: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    balance_date = None
    if opening_balance_date.strip():
        try:
            balance_date = date.fromisoformat(opening_balance_date.strip())
        except ValueError:
            balance_date = "invalid"
    try:
        if balance_date == "invalid":
            raise ValueError("Data do saldo inicial inválida.")
        finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=name,
                account_type=account_type,  # type: ignore[arg-type]
                institution=institution or None,
                opening_balance=opening_balance or None,
                opening_balance_date=balance_date,
            ),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "account_form.html",
            _account_form_context(request, user, db, error=str(exc)),
            status_code=400,
        )
    return _flash_and_redirect(request, "/accounts", success="Conta cadastrada com sucesso.")


@router.get("/accounts/{account_id}/edit", response_class=HTMLResponse)
async def account_edit_page(
    account_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    account = finance.find_account(db, user.id, account_id=account_id)
    if not account:
        return _flash_and_redirect(request, "/accounts", error="Conta não encontrada.")
    return templates.TemplateResponse(
        "account_edit.html",
        _account_form_context(
            request, user, db, account=finance.format_account(account, db=db)
        ),
    )


@router.post("/accounts/{account_id}", response_class=HTMLResponse)
async def update_account_form(
    account_id: int,
    request: Request,
    name: str = Form(...),
    account_type: str = Form(...),
    institution: str = Form(""),
    opening_balance: str = Form(""),
    opening_balance_date: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    balance_date = None
    if opening_balance_date.strip():
        try:
            balance_date = date.fromisoformat(opening_balance_date.strip())
        except ValueError:
            account = finance.find_account(db, user.id, account_id=account_id)
            formatted = finance.format_account(account, db=db) if account else {"id": account_id, "name": name}
            return templates.TemplateResponse(
                "account_edit.html",
                _account_form_context(
                    request, user, db, account=formatted, error="Data do saldo inicial inválida."
                ),
                status_code=400,
            )
    try:
        finance.update_account(
            db,
            user.id,
            UpdateAccountInput(
                account_id=account_id,
                name=name,
                account_type=account_type,  # type: ignore[arg-type]
                institution=institution,
                opening_balance=opening_balance or None,
                opening_balance_date=balance_date,
            ),
        )
    except ValueError as exc:
        account = finance.find_account(db, user.id, account_id=account_id)
        formatted = finance.format_account(account, db=db) if account else {"id": account_id}
        return templates.TemplateResponse(
            "account_edit.html",
            _account_form_context(request, user, db, account=formatted, error=str(exc)),
            status_code=400,
        )
    return _flash_and_redirect(request, "/accounts", success="Conta atualizada com sucesso.")


@router.post("/accounts/{account_id}/delete", response_class=HTMLResponse)
async def delete_account_form(
    account_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        finance.deactivate_account(db, user.id, account_id)
    except ValueError as exc:
        return _flash_and_redirect(request, "/accounts", error=str(exc))
    return _flash_and_redirect(request, "/accounts", success="Conta desativada com sucesso.")


@router.get("/accounts/{account_id}/ofx", response_class=HTMLResponse)
async def account_ofx_upload_page(
    account_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    account = finance.find_account(db, user.id, account_id=account_id)
    if not account:
        return _flash_and_redirect(request, "/accounts", error="Conta não encontrada.")
    ofx_card_import.expire_stale_batches(db, user.id)
    return templates.TemplateResponse(
        "account_ofx_upload.html",
        {
            "request": request,
            "user": user,
            "account": finance.format_account(account, db=db),
            "csrf_token": ensure_csrf_token(request),
            "error": request.session.pop("flash_error", None),
        },
    )


@router.post("/accounts/{account_id}/ofx", response_class=HTMLResponse)
async def account_ofx_upload(
    account_id: int,
    request: Request,
    csrf_token: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    validate_csrf_token(request, csrf_token)
    account = finance.find_account(db, user.id, account_id=account_id)
    if not account:
        return _flash_and_redirect(request, "/accounts", error="Conta não encontrada.")
    try:
        raw = await file.read()
        if not raw:
            raise ValueError("Arquivo de extrato vazio.")
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("Arquivo muito grande (máx. 10 MB).")
        batch = ofx_account_import.create_batch(
            db,
            user.id,
            account,
            filename=file.filename or "extrato.ofx",
            content=raw,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "account_ofx_upload.html",
            {
                "request": request,
                "user": user,
                "account": finance.format_account(account, db=db),
                "csrf_token": ensure_csrf_token(request),
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(
        url=f"/accounts/{account_id}/ofx/{batch.id}",
        status_code=303,
    )


@router.get("/accounts/{account_id}/ofx/{batch_id}", response_class=HTMLResponse)
async def account_ofx_review_page(
    account_id: int,
    batch_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    account = finance.find_account(db, user.id, account_id=account_id)
    if not account:
        return _flash_and_redirect(request, "/accounts", error="Conta não encontrada.")
    try:
        batch = ofx_account_import.get_batch(db, user.id, account_id, batch_id)
        review = ofx_account_import.batch_review_context(db, batch)
    except ValueError as exc:
        return _flash_and_redirect(request, f"/accounts/{account_id}/ofx", error=str(exc))
    return templates.TemplateResponse(
        "account_ofx_review.html",
        {
            "request": request,
            "user": user,
            "account": finance.format_account(account, db=db),
            "review": review,
            "csrf_token": ensure_csrf_token(request),
            "error": request.session.pop("flash_error", None),
        },
    )


@router.post("/accounts/{account_id}/ofx/{batch_id}/apply", response_class=HTMLResponse)
async def account_ofx_apply(
    account_id: int,
    batch_id: int,
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    validate_csrf_token(request, csrf_token)
    account = finance.find_account(db, user.id, account_id=account_id)
    if not account:
        return _flash_and_redirect(request, "/accounts", error="Conta não encontrada.")
    form = await request.form()
    choices: dict[int, dict] = {}
    for key, value in form.multi_items():
        if key.startswith("action_"):
            line_id = int(key.removeprefix("action_"))
            choices.setdefault(line_id, {})["action"] = str(value)
        elif key.startswith("transaction_id_"):
            line_id = int(key.removeprefix("transaction_id_"))
            choices.setdefault(line_id, {})["transaction_id"] = str(value)
        elif key.startswith("category_id_"):
            line_id = int(key.removeprefix("category_id_"))
            choices.setdefault(line_id, {})["category_id"] = str(value)
    try:
        summary = ofx_account_import.apply_batch(db, user.id, account, batch_id, choices)
        msg = ofx_account_import.format_apply_summary(summary)
    except ValueError as exc:
        return _flash_and_redirect(
            request,
            f"/accounts/{account_id}/ofx/{batch_id}",
            error=str(exc),
        )
    return _flash_and_redirect(request, "/accounts", success=msg)


@router.post("/accounts/{account_id}/ofx/{batch_id}/cancel", response_class=HTMLResponse)
async def account_ofx_cancel(
    account_id: int,
    batch_id: int,
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    validate_csrf_token(request, csrf_token)
    try:
        ofx_account_import.cancel_batch(db, user.id, account_id, batch_id)
    except ValueError as exc:
        return _flash_and_redirect(request, "/accounts", error=str(exc))
    return _flash_and_redirect(
        request, "/accounts", success="Importação OFX descartada."
    )


@router.post("/accounts/cards", response_class=HTMLResponse)
async def create_card_form(
    request: Request,
    name: str = Form(...),
    institution: str = Form(""),
    closing_day: int = Form(...),
    due_day: int = Form(...),
    credit_limit: str = Form(""),
    settlement_account_id: int | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    try:
        if not settlement_account_id:
            raise ValueError("Selecione a conta de liquidação do cartão.")
        settlement = db.get(Account, settlement_account_id)
        if not settlement or settlement.user_id != user.id:
            raise ValueError("Conta de liquidação inválida.")
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=name,
                institution=institution or None,
                closing_day=closing_day,
                due_day=due_day,
                credit_limit=credit_limit or None,
                settlement_account_name=settlement.name,
            ),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "card_form.html",
            _card_form_context(request, user, db, error=str(exc)),
            status_code=400,
        )
    return _flash_and_redirect(
        request, "/accounts/cards", success="Cartão cadastrado com sucesso."
    )


@router.get("/accounts/cards/{card_id}/edit", response_class=HTMLResponse)
async def card_edit_page(
    card_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    from app.services.credit_cards import format_credit_card

    card = finance.find_card(db, user.id, card_id=card_id)
    if not card:
        return _flash_and_redirect(
            request, "/accounts/cards", error="Cartão não encontrado."
        )
    return templates.TemplateResponse(
        "card_edit.html",
        _card_form_context(request, user, db, card=format_credit_card(card, db=db)),
    )


@router.post("/accounts/cards/{card_id}", response_class=HTMLResponse)
async def update_card_form(
    card_id: int,
    request: Request,
    name: str = Form(...),
    institution: str = Form(""),
    closing_day: int = Form(...),
    due_day: int = Form(...),
    credit_limit: str = Form(""),
    settlement_account_id: int | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    from app.services.credit_cards import format_credit_card

    try:
        if not settlement_account_id:
            raise ValueError("Selecione a conta de liquidação do cartão.")
        settlement = db.get(Account, settlement_account_id)
        if not settlement or settlement.user_id != user.id:
            raise ValueError("Conta de liquidação inválida.")
        finance.update_card(
            db,
            user.id,
            UpdateCardInput(
                card_id=card_id,
                name=name,
                institution=institution,
                closing_day=closing_day,
                due_day=due_day,
                credit_limit=credit_limit,
                settlement_account_name=settlement.name,
            ),
        )
    except ValueError as exc:
        card = finance.find_card(db, user.id, card_id=card_id)
        formatted = format_credit_card(card, db=db) if card else {"id": card_id, "name": name}
        return templates.TemplateResponse(
            "card_edit.html",
            _card_form_context(request, user, db, card=formatted, error=str(exc)),
            status_code=400,
        )
    return _flash_and_redirect(
        request, "/accounts/cards", success="Cartão atualizado com sucesso."
    )


@router.post("/accounts/cards/{card_id}/delete", response_class=HTMLResponse)
async def delete_card_form(
    card_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        finance.deactivate_card(db, user.id, DeleteCardInput(card_id=card_id))
    except ValueError as exc:
        return _flash_and_redirect(request, "/accounts/cards", error=str(exc))
    return _flash_and_redirect(
        request, "/accounts/cards", success="Cartão desativado com sucesso."
    )


@router.get("/accounts/cards/{card_id}/ofx", response_class=HTMLResponse)
async def card_ofx_upload_page(
    card_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    from app.services.credit_cards import format_credit_card

    card = finance.find_card(db, user.id, card_id=card_id)
    if not card:
        return _flash_and_redirect(
            request, "/accounts/cards", error="Cartão não encontrado."
        )
    ofx_card_import.expire_stale_batches(db, user.id)
    return templates.TemplateResponse(
        "card_ofx_upload.html",
        {
            "request": request,
            "user": user,
            "card": format_credit_card(card, db=db),
            "csrf_token": ensure_csrf_token(request),
            "error": request.session.pop("flash_error", None),
        },
    )


@router.post("/accounts/cards/{card_id}/ofx", response_class=HTMLResponse)
async def card_ofx_upload(
    card_id: int,
    request: Request,
    csrf_token: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    from app.services.credit_cards import format_credit_card

    validate_csrf_token(request, csrf_token)
    card = finance.find_card(db, user.id, card_id=card_id)
    if not card:
        return _flash_and_redirect(
            request, "/accounts/cards", error="Cartão não encontrado."
        )
    try:
        raw = await file.read()
        if not raw:
            raise ValueError("Arquivo de extrato vazio.")
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("Arquivo muito grande (máx. 10 MB).")
        batch = ofx_card_import.create_batch(
            db,
            user.id,
            card,
            filename=file.filename or "extrato.ofx",
            content=raw,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "card_ofx_upload.html",
            {
                "request": request,
                "user": user,
                "card": format_credit_card(card, db=db),
                "csrf_token": ensure_csrf_token(request),
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(
        url=f"/accounts/cards/{card_id}/ofx/{batch.id}",
        status_code=303,
    )


@router.get("/accounts/cards/{card_id}/ofx/{batch_id}", response_class=HTMLResponse)
async def card_ofx_review_page(
    card_id: int,
    batch_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    from app.services.credit_cards import format_credit_card

    card = finance.find_card(db, user.id, card_id=card_id)
    if not card:
        return _flash_and_redirect(
            request, "/accounts/cards", error="Cartão não encontrado."
        )
    try:
        batch = ofx_card_import.get_batch(db, user.id, card_id, batch_id)
        review = ofx_card_import.batch_review_context(db, batch)
    except ValueError as exc:
        return _flash_and_redirect(request, f"/accounts/cards/{card_id}/ofx", error=str(exc))
    return templates.TemplateResponse(
        "card_ofx_review.html",
        {
            "request": request,
            "user": user,
            "card": format_credit_card(card, db=db),
            "review": review,
            "csrf_token": ensure_csrf_token(request),
            "error": request.session.pop("flash_error", None),
        },
    )


@router.post("/accounts/cards/{card_id}/ofx/{batch_id}/apply", response_class=HTMLResponse)
async def card_ofx_apply(
    card_id: int,
    batch_id: int,
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    validate_csrf_token(request, csrf_token)
    card = finance.find_card(db, user.id, card_id=card_id)
    if not card:
        return _flash_and_redirect(
            request, "/accounts/cards", error="Cartão não encontrado."
        )
    form = await request.form()
    choices: dict[int, dict] = {}
    for key, value in form.multi_items():
        if key.startswith("action_"):
            line_id = int(key.removeprefix("action_"))
            choices.setdefault(line_id, {})["action"] = str(value)
        elif key.startswith("transaction_id_"):
            line_id = int(key.removeprefix("transaction_id_"))
            choices.setdefault(line_id, {})["transaction_id"] = str(value)
        elif key.startswith("invoice_id_"):
            line_id = int(key.removeprefix("invoice_id_"))
            choices.setdefault(line_id, {})["invoice_id"] = str(value)
        elif key.startswith("category_id_"):
            line_id = int(key.removeprefix("category_id_"))
            choices.setdefault(line_id, {})["category_id"] = str(value)
    try:
        summary = ofx_card_import.apply_batch(db, user.id, card, batch_id, choices)
        msg = ofx_card_import.format_apply_summary(summary)
    except ValueError as exc:
        return _flash_and_redirect(
            request,
            f"/accounts/cards/{card_id}/ofx/{batch_id}",
            error=str(exc),
        )
    return _flash_and_redirect(request, "/accounts/cards", success=msg)


@router.post("/accounts/cards/{card_id}/ofx/{batch_id}/cancel", response_class=HTMLResponse)
async def card_ofx_cancel(
    card_id: int,
    batch_id: int,
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    validate_csrf_token(request, csrf_token)
    try:
        ofx_card_import.cancel_batch(db, user.id, card_id, batch_id)
    except ValueError as exc:
        return _flash_and_redirect(request, "/accounts/cards", error=str(exc))
    return _flash_and_redirect(
        request, "/accounts/cards", success="Importação OFX descartada."
    )


@router.post("/accounts/invoices/{invoice_id}/pay", response_class=HTMLResponse)
async def pay_invoice_form(
    invoice_id: int,
    request: Request,
    from_account_id: int = Form(...),
    payment_date: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    scope = read_scope_id(user)
    from app.services.credit_cards import pay_invoice
    from app.models import Account

    try:
        from_account = db.get(Account, from_account_id)
        if not from_account or from_account.user_id != user.id:
            raise ValueError("Conta de débito inválida.")
        pay_dt = None
        if payment_date.strip():
            pay_dt = date.fromisoformat(payment_date.strip())
        pay_invoice(
            db,
            user.id,
            invoice_id=invoice_id,
            from_account_name=from_account.name,
            payment_date=pay_dt,
        )
        return templates.TemplateResponse(
            "accounts.html",
            _build_accounts_context(
                request, user, db, scope, focus_cards=True, success="Fatura paga com sucesso."
            ),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "accounts.html",
            _build_accounts_context(
                request, user, db, scope, focus_cards=True, error=str(exc)
            ),
        )


@router.post("/accounts/invoices/{invoice_id}/delete", response_class=HTMLResponse)
async def delete_invoice_form(
    invoice_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    from app.services.credit_cards import delete_invoice

    try:
        result = delete_invoice(db, user.id, invoice_id)
        n = result["deleted_movements"]
        if n == 0:
            msg = "Fatura excluída."
        elif n == 1:
            msg = "Fatura excluída (1 movimento do cartão removido)."
        else:
            msg = f"Fatura excluída ({n} movimentos do cartão removidos)."
        if result.get("payment_kept"):
            msg += " O pagamento na conta bancária foi mantido."
        return _flash_and_redirect(request, "/accounts/cards", success=msg)
    except ValueError as exc:
        return _flash_and_redirect(request, "/accounts/cards", error=str(exc))


@router.post("/accounts/deactivate", response_class=HTMLResponse)
async def deactivate_account_form(
    request: Request,
    account_id: int = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        finance.deactivate_account(db, user.id, account_id)
    except ValueError as exc:
        return _flash_and_redirect(request, "/accounts", error=str(exc))
    return _flash_and_redirect(request, "/accounts", success="Conta desativada com sucesso.")


@router.post("/transactions", response_class=HTMLResponse)
async def create_transaction_form(
    request: Request,
    account_id: str | None = Form(None),
    card_id: str | None = Form(None),
    from_account_id: str | None = Form(None),
    to_account_id: str | None = Form(None),
    category_id: str | None = Form(None),
    type: str = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    competence_date: str | None = Form(None),
    due_date: str | None = Form(None),
    payment_date: str | None = Form(None),
    is_planned: str | None = Form(None),
    is_recurring: str | None = Form(None),
    frequency: str | None = Form(None),
    recurrence_end_date: str | None = Form(None),
    is_installmented: str | None = Form(None),
    installment_count: str | None = Form(None),
    installment_interval: str | None = Form(None),
    installment_amount_basis: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    account_id = _form_optional_int(account_id)
    card_id = _form_optional_int(card_id)
    from_account_id = _form_optional_int(from_account_id)
    to_account_id = _form_optional_int(to_account_id)
    category_id = _form_optional_int(category_id)
    installment_count = _form_optional_int(installment_count)

    try:
        if type == "transfer":
            from_acc = db.get(Account, from_account_id)
            to_acc = db.get(Account, to_account_id)
            if not from_acc or not to_acc or from_acc.user_id != user.id or to_acc.user_id != user.id:
                raise ValueError("Contas de origem e destino inválidas.")
            from app.schemas import RegisterTransferInput

            pay_date = (
                date.fromisoformat(payment_date)
                if payment_date
                else local_today()
            )
            finance.register_transfer(
                db,
                user.id,
                RegisterTransferInput(
                    amount=amount,
                    from_account_name=from_acc.name,
                    to_account_name=to_acc.name,
                    description=description or None,
                    payment_date=pay_date,
                ),
            )
            success = "Transferência registrada com sucesso."
        else:
            if account_id is None and card_id is None:
                raise ValueError("Informe a conta ou o cartão.")
            planned = is_planned == "on" or card_id is not None
            if planned:
                if not competence_date or not due_date:
                    raise ValueError("Competência e vencimento são obrigatórios para previsto.")
                comp = date.fromisoformat(competence_date)
                due = date.fromisoformat(due_date)
                pay = None
            else:
                pay = (
                    date.fromisoformat(payment_date)
                    if payment_date
                    else local_today()
                )
                comp = date.fromisoformat(competence_date) if competence_date else None
                due = date.fromisoformat(due_date) if due_date else None
            rec_end = None
            if recurrence_end_date and recurrence_end_date.strip():
                rec_end = date.fromisoformat(recurrence_end_date.strip())
            rec_freq = frequency if is_recurring == "on" and frequency else None
            if rec_freq and not planned:
                raise ValueError("Lançamento fixo deve ser cadastrado como previsto.")
            inst_count = installment_count if is_installmented == "on" and installment_count else None
            inst_interval = installment_interval if is_installmented == "on" and installment_interval else None
            if inst_count and rec_freq:
                raise ValueError("Não é possível combinar lançamento fixo e parcelado.")
            if inst_count and inst_count < 2:
                raise ValueError("Parcelamento exige pelo menos 2 parcelas.")
            if inst_count and installment_amount_basis not in {"total", "installment"}:
                raise ValueError(
                    "Informe se o valor é o total da compra ou o valor de cada parcela."
                )
            finance.create_user_transaction(
                db,
                user.id,
                TransactionCreate(
                    account_id=account_id,
                    card_id=card_id,
                    category_id=category_id,
                    type=type,
                    amount_cents=decimal_to_cents(amount),
                    description=description or "Lançamento",
                    competence_date=comp,
                    due_date=due,
                    payment_date=pay,
                    status="planned" if planned else "actual",
                ),
                frequency=rec_freq,
                recurrence_end_date=rec_end,
                installment_count=inst_count,
                installment_interval=inst_interval,
                installment_amount_basis=installment_amount_basis if inst_count else None,
            )
            success = (
                "Parcelamento registrado com sucesso."
                if inst_count
                else (
                    "Série fixa registrada com sucesso."
                    if rec_freq
                    else (
                        "Previsão registrada com sucesso."
                        if planned
                        else "Transação registrada com sucesso."
                    )
                )
            )
    except (ValueError, ValidationError) as exc:
        return templates.TemplateResponse(
            "transaction_form.html",
            _transaction_form_context(request, user, db, error=str(exc)),
            status_code=400,
        )

    return _flash_and_redirect_transactions(request, success=success)


@router.get("/transactions/{tx_id}/edit", response_class=HTMLResponse)
async def transaction_edit_page(
    tx_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    tx = finance.find_transaction(db, user.id, transaction_id=tx_id)
    if not tx:
        return _flash_and_redirect_transactions(
            request, error="Lançamento não encontrado."
        )
    if tx.type in {"transfer_out", "transfer_in"} and tx.transfer_group_id:
        out = finance.find_transfer(db, user.id, transaction_id=tx_id)
        if out:
            tx = out
    formatted = finance.format_transaction(tx)
    if tx.type == "transfer_out":
        formatted["from_account_id"] = tx.account_id
        formatted["to_account_id"] = tx.counterparty_account_id
    return templates.TemplateResponse(
        "transaction_edit.html",
        _transaction_form_context(request, user, db, tx=formatted),
    )


@router.post("/transactions/{tx_id}", response_class=HTMLResponse)
async def update_transaction_form(
    tx_id: int,
    request: Request,
    amount: str = Form(...),
    description: str = Form(""),
    account_id: str | None = Form(None),
    category_id: str | None = Form(None),
    from_account_id: str | None = Form(None),
    to_account_id: str | None = Form(None),
    type: str | None = Form(None),
    competence_date: str | None = Form(None),
    due_date: str | None = Form(None),
    payment_date: str | None = Form(None),
    installment_scope: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    account_id = _form_optional_int(account_id)
    category_id = _form_optional_int(category_id)
    from_account_id = _form_optional_int(from_account_id)
    to_account_id = _form_optional_int(to_account_id)
    tx = finance.find_transaction(db, user.id, transaction_id=tx_id)
    if not tx:
        return _flash_and_redirect_transactions(
            request, error="Lançamento não encontrado."
        )

    try:
        if tx.type in {"transfer_out", "transfer_in"}:
            from_acc = db.get(Account, from_account_id) if from_account_id else None
            to_acc = db.get(Account, to_account_id) if to_account_id else None
            if from_account_id and (not from_acc or from_acc.user_id != user.id):
                raise ValueError("Conta de origem inválida.")
            if to_account_id and (not to_acc or to_acc.user_id != user.id):
                raise ValueError("Conta de destino inválida.")
            pay = date.fromisoformat(payment_date) if payment_date else None
            finance.update_transfer(
                db,
                user.id,
                UpdateTransferInput(
                    transaction_id=tx_id,
                    amount=amount,
                    description=description or None,
                    from_account_name=from_acc.name if from_acc else None,
                    to_account_name=to_acc.name if to_acc else None,
                    payment_date=pay,
                    transaction_date=pay,
                ),
            )
            success = "Transferência atualizada com sucesso."
        else:
            account = db.get(Account, account_id) if account_id else None
            if account_id and (not account or account.user_id != user.id):
                raise ValueError("Conta inválida.")
            original_type = tx.type
            new_type = type if type in {"expense", "income"} else original_type
            category = db.get(Category, category_id) if category_id else None
            if category_id and (not category or category.user_id != user.id):
                raise ValueError("Categoria inválida.")
            if category and category.type != new_type:
                raise ValueError(
                    "A categoria escolhida não corresponde ao tipo do lançamento."
                )
            from app.services.installments import count_subsequent_installments

            subsequent = count_subsequent_installments(db, user.id, tx)
            scope = installment_scope if installment_scope in {"this", "subsequent"} else None
            if subsequent > 0 and scope is None:
                raise ValueError(
                    "Escolha se deseja atualizar só esta parcela ou esta e as seguintes."
                )
            comp = date.fromisoformat(competence_date) if competence_date else None
            due = date.fromisoformat(due_date) if due_date else None
            pay = date.fromisoformat(payment_date) if payment_date else None
            finance.update_transaction(
                db,
                user.id,
                UpdateTransactionInput(
                    transaction_id=tx_id,
                    amount=amount,
                    description=description or None,
                    account_name=account.name if account else None,
                    category_name=category.name if category else None,
                    type=new_type if new_type != original_type else None,
                    competence_date=comp,
                    due_date=due,
                    payment_date=pay,
                    installment_scope=scope,
                ),
            )
            if scope == "subsequent" and subsequent > 0:
                success = (
                    f"Lançamento e {subsequent} parcela(s) seguinte(s) atualizados."
                )
            else:
                success = "Lançamento atualizado com sucesso."
    except (ValueError, ValidationError) as exc:
        formatted = finance.format_transaction(tx)
        if tx.type in {"transfer_out", "transfer_in"}:
            out = finance.find_transfer(db, user.id, transaction_id=tx_id) or tx
            formatted = finance.format_transaction(out)
            formatted["from_account_id"] = from_account_id or out.account_id
            formatted["to_account_id"] = to_account_id
        return templates.TemplateResponse(
            "transaction_edit.html",
            _transaction_form_context(
                request, user, db, tx=formatted, error=str(exc)
            ),
            status_code=400,
        )

    return _flash_and_redirect_transactions(request, success=success)


@router.post("/transactions/{tx_id}/delete", response_class=HTMLResponse)
async def delete_transaction_form(
    tx_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        finance.delete_transaction(
            db, user.id, DeleteTransactionInput(transaction_id=tx_id)
        )
    except ValueError as exc:
        return _flash_and_redirect_transactions(request, error=str(exc))
    return _flash_and_redirect_transactions(
        request, success="Lançamento excluído com sucesso."
    )


@router.post("/transactions/{planned_id}/realize", response_class=HTMLResponse)
async def realize_planned_form(
    planned_id: int,
    request: Request,
    amount: str | None = Form(None),
    payment_date: date = Form(...),
    description: str = Form(""),
    same_account: str = Form("yes"),
    account_name: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    realize_kwargs: dict = {
        "planned_id": planned_id,
        "amount": amount if amount and amount.strip() else None,
        "payment_date": payment_date,
        "description": description or None,
    }
    if same_account.strip().lower() in {"no", "não", "nao"} and not account_name.strip():
        return templates.TemplateResponse(
            "transactions.html",
            _transactions_page_context(
                request,
                user,
                db,
                error="Informe a conta para realização.",
            ),
            status_code=400,
        )
    if same_account.strip().lower() in {"no", "não", "nao"}:
        realize_kwargs["account_name"] = account_name.strip()
    try:
        finance.realize_planned(
            db,
            user.id,
            RealizePlannedInput(**realize_kwargs),
        )
    except ValueError as exc:
        ctx = _transactions_page_context(request, user, db)
        ctx["error"] = str(exc)
        return templates.TemplateResponse(
            "transactions.html",
            ctx,
            status_code=400,
        )
    return templates.TemplateResponse(
        "transactions.html",
        _transactions_page_context(
            request, user, db, success="Previsto realizado com sucesso."
        ),
    )


@router.post("/transactions/recurring/{rule_id}/stop", response_class=HTMLResponse)
async def stop_recurring_rule(
    rule_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    from app.services.recurrence import deactivate_recurring_rule

    try:
        deactivate_recurring_rule(db, user.id, rule_id)
    except ValueError as exc:
        return templates.TemplateResponse(
            "transactions.html",
            _transactions_page_context(request, user, db, error=str(exc)),
            status_code=400,
        )
    return templates.TemplateResponse(
        "transactions.html",
        _transactions_page_context(
            request, user, db, success="Série fixa encerrada. Previstos pendentes removidos."
        ),
    )


@router.post("/transactions/installments/{plan_id}/stop", response_class=HTMLResponse)
async def stop_installment_plan(
    plan_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    from app.services.installments import cancel_installment_plan

    try:
        cancel_installment_plan(db, user.id, plan_id)
    except ValueError as exc:
        return templates.TemplateResponse(
            "transactions.html",
            _transactions_page_context(request, user, db, error=str(exc)),
            status_code=400,
        )
    return templates.TemplateResponse(
        "transactions.html",
        _transactions_page_context(
            request, user, db, success="Parcelas pendentes canceladas."
        ),
    )


@router.get("/budgets", response_class=HTMLResponse)
async def budgets_page(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    scope = read_scope_id(user)
    finance.seed_defaults(db, user.id)
    today = local_today()
    year = year or today.year
    month = month or today.month
    budgets = finance.get_budget_status(
        db, scope, BudgetStatusInput(year=year, month=month)
    )
    flash_success, flash_error = _consume_flash(request)
    categories = (
        db.query(Category)
        .filter(Category.user_id == user.id, Category.type == "expense")
        .order_by(Category.name)
        .all()
    )
    return templates.TemplateResponse(
        "budgets.html",
        {
            "request": request,
            "user": user,
            "is_root": user.is_root,
            "budgets": budgets,
            "categories": categories,
            "today": today,
            "year": year,
            "month": month,
            "success": flash_success,
            "error": flash_error,
        },
    )


def _budget_form_context(
    request: Request,
    user: User,
    db: Session,
    *,
    budget: dict | None = None,
    success: str | None = None,
    error: str | None = None,
) -> dict:
    finance.seed_defaults(db, user.id)
    today = local_today()
    categories = (
        db.query(Category)
        .filter(Category.user_id == user.id, Category.type == "expense")
        .order_by(Category.name)
        .all()
    )
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "budget": budget,
        "categories": categories,
        "today": today,
        "success": success,
        "error": error,
    }


@router.get("/budgets/new", response_class=HTMLResponse)
async def budget_new_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    return templates.TemplateResponse(
        "budget_form.html",
        _budget_form_context(request, user, db),
    )


@router.post("/budgets", response_class=HTMLResponse)
async def create_budget_form(
    request: Request,
    category_id: int = Form(...),
    year: int = Form(...),
    month: int = Form(...),
    limit: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    try:
        finance.create_budget(
            db,
            user.id,
            BudgetCreate(
                category_id=category_id,
                year=year,
                month=month,
                limit_cents=decimal_to_cents(limit),
            ),
        )
    except (ValueError, ValidationError) as exc:
        return templates.TemplateResponse(
            "budget_form.html",
            _budget_form_context(request, user, db, error=str(exc)),
            status_code=400,
        )
    return _flash_and_redirect(
        request,
        f"/budgets?year={year}&month={month}",
        success="Orçamento definido com sucesso.",
    )


@router.get("/budgets/{budget_id}/edit", response_class=HTMLResponse)
async def budget_edit_page(
    budget_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    budget = finance.get_budget(db, user.id, budget_id)
    if not budget:
        return _flash_and_redirect(request, "/budgets", error="Orçamento não encontrado.")
    return templates.TemplateResponse(
        "budget_edit.html",
        _budget_form_context(request, user, db, budget=budget),
    )


@router.post("/budgets/{budget_id}", response_class=HTMLResponse)
async def update_budget_form(
    budget_id: int,
    request: Request,
    category_id: int = Form(...),
    year: int = Form(...),
    month: int = Form(...),
    limit: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    try:
        finance.update_budget(
            db,
            user.id,
            budget_id,
            category_id=category_id,
            year=year,
            month=month,
            limit_cents=decimal_to_cents(limit),
        )
    except (ValueError, ValidationError) as exc:
        budget = finance.get_budget(db, user.id, budget_id) or {
            "id": budget_id,
            "category_id": category_id,
            "year": year,
            "month": month,
            "limit": limit,
        }
        return templates.TemplateResponse(
            "budget_edit.html",
            _budget_form_context(request, user, db, budget=budget, error=str(exc)),
            status_code=400,
        )
    return _flash_and_redirect(
        request,
        f"/budgets?year={year}&month={month}",
        success="Orçamento atualizado com sucesso.",
    )


@router.post("/budgets/{budget_id}/delete", response_class=HTMLResponse)
async def delete_budget_form(
    budget_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        budget = finance.get_budget(db, user.id, budget_id)
        finance.delete_budget(db, user.id, budget_id)
        year = budget["year"] if budget else local_today().year
        month = budget["month"] if budget else local_today().month
    except ValueError as exc:
        return _flash_and_redirect(request, "/budgets", error=str(exc))
    return _flash_and_redirect(
        request,
        f"/budgets?year={year}&month={month}",
        success="Orçamento excluído com sucesso.",
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    from app.services import db_backup

    templates = get_templates(request)
    users = admin.list_users_overview(db)
    summary = finance.get_summary(db, None, SummaryInput())
    flash_success, flash_error = _consume_flash(request)
    backups = db_backup.list_backups()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "is_root": True,
            "users": users,
            "summary": summary,
            "backups": backups,
            "restore_confirm_word": db_backup.RESTORE_CONFIRM_WORD,
            "success": flash_success,
            "error": flash_error,
            "today": local_today(),
            "csrf_token": ensure_csrf_token(request),
        },
    )


@router.get("/admin/users/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(
    request: Request,
    user_id: int,
    user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    detail = admin.get_user_detail(db, user_id)
    return templates.TemplateResponse(
        "admin_user.html",
        {
            "request": request,
            "user": user,
            "is_root": True,
            "profile": detail["profile"],
            "summary": detail["summary"],
            "accounts": detail["accounts"],
            "transactions": detail["transactions"],
            "budgets": detail["budgets"],
            "categories": detail["categories"],
            "today": local_today(),
            "csrf_token": ensure_csrf_token(request),
        },
    )


@router.post("/admin/users/{user_id}/approve")
async def admin_approve_user(
    request: Request,
    user_id: int,
    csrf_token: str = Form(...),
    user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    validate_csrf_token(request, csrf_token)
    admin.set_user_active(db, user_id, active=True)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/revoke")
async def admin_revoke_user(
    request: Request,
    user_id: int,
    csrf_token: str = Form(...),
    user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    validate_csrf_token(request, csrf_token)
    admin.set_user_active(db, user_id, active=False)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/backup/create")
async def admin_backup_create(
    request: Request,
    csrf_token: str = Form(...),
    user: User = Depends(require_root),
):
    from app.services import db_backup

    validate_csrf_token(request, csrf_token)
    try:
        info = db_backup.create_backup()
        return _flash_and_redirect(
            request,
            "/admin",
            success=f"Backup criado: {info.filename} ({info.size_label}).",
        )
    except ValueError as exc:
        return _flash_and_redirect(request, "/admin", error=str(exc))


@router.post("/admin/backup/restore")
async def admin_backup_restore(
    request: Request,
    filename: str = Form(...),
    confirm: str = Form(...),
    csrf_token: str = Form(...),
    user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    from app.services import db_backup

    validate_csrf_token(request, csrf_token)
    # Invalidate a conexão da request antes do terminate_backend do restore.
    try:
        db.invalidate()
    except Exception:
        pass
    try:
        restored = db_backup.restore_backup(filename, confirm=confirm)
        return _flash_and_redirect(
            request,
            "/admin",
            success=(
                f"Banco restaurado a partir de {restored}. "
                "Faça logout e login se a sessão ficar inconsistente."
            ),
        )
    except ValueError as exc:
        return _flash_and_redirect(request, "/admin", error=str(exc))
    except Exception as exc:
        return _flash_and_redirect(
            request,
            "/admin",
            error=f"Falha inesperada na restauração: {exc}",
        )


@router.post("/admin/backup/delete")
async def admin_backup_delete(
    request: Request,
    filename: str = Form(...),
    csrf_token: str = Form(...),
    user: User = Depends(require_root),
):
    from app.services import db_backup

    validate_csrf_token(request, csrf_token)
    try:
        db_backup.delete_backup(filename)
        return _flash_and_redirect(
            request, "/admin", success=f"Backup {filename} excluído."
        )
    except ValueError as exc:
        return _flash_and_redirect(request, "/admin", error=str(exc))


@router.get("/admin/backup/download/{filename}")
async def admin_backup_download(
    filename: str,
    user: User = Depends(require_root),
):
    from fastapi.responses import FileResponse

    from app.services import db_backup

    try:
        path = db_backup.backup_path(filename)
        if not path.is_file():
            raise ValueError("Arquivo de backup não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


def _log_chat_exchange(
    db,
    user_id: int,
    session: dict,
    user_message: str,
    agent_message: str,
    *,
    tool_used: str | None = None,
    source: str | None = None,
    metadata: dict | None = None,
) -> None:
    conversation = get_or_create_conversation(db, user_id, session)
    log_message(
        db,
        conversation_id=conversation.id,
        user_id=user_id,
        role="user",
        content=user_message,
        source=source,
    )
    log_message(
        db,
        conversation_id=conversation.id,
        user_id=user_id,
        role="assistant",
        content=agent_message,
        tool_used=tool_used,
        source=source,
        metadata=metadata,
    )


@router.get("/agent/welcome", response_class=HTMLResponse)
async def agent_welcome(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not consume_login_prompt(request.session):
        return HTMLResponse("")
    templates = get_templates(request)
    result = begin_login_prompt(request.session)
    _log_chat_exchange(
        db,
        user.id,
        request.session,
        "[login]",
        result.message,
        source=result.source,
    )
    return templates.TemplateResponse(
        "partials/agent_assistant_message.html",
        {
            "request": request,
            "user": user,
            "agent_message": result.message,
            "suggestions": result.suggestions,
        },
    )


@router.post("/agent/chat", response_class=HTMLResponse)
async def agent_chat(
    request: Request,
    message: str = Form(...),
    confirmed: str = Form("false"),
    pending_action: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    finance.seed_defaults(db, user.id)

    from app.services.agent_state import clear_agent_flow_state, is_cancel_message

    if is_cancel_message(message, request.session) and confirmed != "true":
        clear_agent_flow_state(request.session)
        _log_chat_exchange(
            db,
            user.id,
            request.session,
            message,
            "Ok, cancelei. Pode enviar um novo pedido.",
            source="cancel",
        )
        return templates.TemplateResponse(
            "partials/agent_response.html",
            {
                "request": request,
                "user": user,
                "user_message": message.capitalize(),
                "agent_message": "Ok, cancelei. Pode enviar um novo pedido.",
                "needs_confirmation": False,
            },
        )

    if confirmed == "true" and pending_action:
        import json

        from app.services.account_wizard import clear_wizard
        from app.services.category_wizard import clear_wizard as clear_category_wizard
        from app.services.multi_movement_flow import (
            clear_pending_movements,
            execute_batch_movements,
        )

        parsed_action = json.loads(pending_action)
        if parsed_action.get("batch"):
            response = execute_batch_movements(db, user.id, parsed_action)
            clear_pending_movements(request.session)
            clear_transaction_wizard(request.session)
            _log_chat_exchange(
                db,
                user.id,
                request.session,
                "Confirmar",
                response,
                tool_used="register_expense",
                source="confirmation",
                metadata={"pending_action": parsed_action},
            )
            return templates.TemplateResponse(
                "partials/agent_response.html",
                {
                    "request": request,
                    "user": user,
                    "user_message": "Confirmar",
                    "agent_message": response,
                    "needs_confirmation": False,
                    "refresh_page": True,
                    "keep_chat_open": True,
                },
            )

        try:
            tool_call = ToolCall(**parsed_action)
        except ValidationError as exc:
            error_message = f"Não foi possível concluir a ação: {exc}"
            _log_chat_exchange(
                db,
                user.id,
                request.session,
                "Confirmar",
                error_message,
                source="confirmation_error",
                metadata={"pending_action": parsed_action},
            )
            return templates.TemplateResponse(
                "partials/agent_response.html",
                {
                    "request": request,
                    "user": user,
                    "user_message": "Confirmar",
                    "agent_message": error_message,
                    "needs_confirmation": True,
                    "pending_action": parsed_action,
                    "keep_chat_open": True,
                },
            )

        try:
            outcome = execute_tool(db, user.id, tool_call)
        except (ValidationError, ValueError) as exc:
            _log_chat_exchange(
                db,
                user.id,
                request.session,
                "Confirmar",
                f"Não foi possível concluir a ação: {exc}",
                tool_used=tool_call.tool,
                source="confirmation_error",
                metadata={"pending_action": parsed_action},
            )
            return templates.TemplateResponse(
                "partials/agent_response.html",
                {
                    "request": request,
                    "user": user,
                    "user_message": "Confirmar",
                    "agent_message": f"Não foi possível concluir a ação: {exc}",
                    "needs_confirmation": True,
                    "pending_action": parsed_action,
                    "keep_chat_open": True,
                },
            )
        response = format_tool_result(outcome["action"], outcome["result"])
        if tool_call.tool == "create_card":
            from app.services.card_wizard import clear_wizard as clear_card_wizard

            clear_card_wizard(request.session)
            created_name = None
            if isinstance(outcome.get("result"), dict):
                created_name = outcome["result"].get("name")
            if created_name:
                from app.services.transaction_wizard import (
                    resume_paused_transaction_after_create,
                )

                resumed = resume_paused_transaction_after_create(
                    request.session,
                    db=db,
                    user_id=user.id,
                    card_name=created_name,
                )
                if resumed:
                    _log_chat_exchange(
                        db,
                        user.id,
                        request.session,
                        "Confirmar",
                        resumed.message,
                        tool_used=resumed.tool_used or "create_card",
                        source="confirmation",
                        metadata={
                            "pending_action": resumed.pending_action,
                            "resumed_after_card": True,
                        },
                    )
                    return templates.TemplateResponse(
                        "partials/agent_response.html",
                        {
                            "request": request,
                            "user": user,
                            "user_message": "Confirmar",
                            "agent_message": resumed.message,
                            "needs_confirmation": resumed.needs_confirmation,
                            "pending_action": resumed.pending_action,
                            "suggestions": resumed.suggestions,
                            "keep_chat_open": True,
                        },
                    )
        if tool_call.tool == "create_account":
            clear_wizard(request.session)
            created_name = None
            if isinstance(outcome.get("result"), dict):
                created_name = outcome["result"].get("name")
            if created_name:
                from app.services.transaction_wizard import (
                    get_paused_wizard,
                    resume_paused_transaction_after_create,
                )

                if get_paused_wizard(request.session):
                    resumed = resume_paused_transaction_after_create(
                        request.session,
                        db=db,
                        user_id=user.id,
                        account_name=created_name,
                    )
                    if resumed:
                        _log_chat_exchange(
                            db,
                            user.id,
                            request.session,
                            "Confirmar",
                            resumed.message,
                            tool_used=resumed.tool_used or "create_account",
                            source="confirmation",
                            metadata={
                                "pending_action": resumed.pending_action,
                                "resumed_after_account": True,
                            },
                        )
                        return templates.TemplateResponse(
                            "partials/agent_response.html",
                            {
                                "request": request,
                                "user": user,
                                "user_message": "Confirmar",
                                "agent_message": resumed.message,
                                "needs_confirmation": resumed.needs_confirmation,
                                "pending_action": resumed.pending_action,
                                "suggestions": resumed.suggestions,
                                "keep_chat_open": True,
                            },
                        )
        if tool_call.tool == "create_category":
            clear_category_wizard(request.session)
            from app.services.transaction_wizard import (
                resume_paused_transaction_after_category,
            )

            created_name = None
            if isinstance(outcome.get("result"), dict):
                created_name = outcome["result"].get("name")
            if created_name:
                resumed = resume_paused_transaction_after_category(
                    request.session, category_name=created_name
                )
                if resumed:
                    _log_chat_exchange(
                        db,
                        user.id,
                        request.session,
                        "Confirmar",
                        resumed.message,
                        tool_used=resumed.tool_used or "create_category",
                        source="confirmation",
                        metadata={
                            "pending_action": resumed.pending_action,
                            "resumed_after_category": True,
                        },
                    )
                    return templates.TemplateResponse(
                        "partials/agent_response.html",
                        {
                            "request": request,
                            "user": user,
                            "user_message": "Confirmar",
                            "agent_message": resumed.message,
                            "needs_confirmation": resumed.needs_confirmation,
                            "pending_action": resumed.pending_action,
                            "suggestions": resumed.suggestions,
                            "keep_chat_open": True,
                        },
                    )
        if tool_call.tool in {"register_expense", "register_income", "register_transfer", "realize_planned", "update_transfer", "update_transaction", "update_account", "update_card", "delete_card", "delete_transaction"}:
            clear_transaction_wizard(request.session)
            from app.services.realize_planned_slots import (
                clear_wizard as clear_realize_planned_wizard,
            )
            from app.services.transfer_slots import clear_wizard as clear_transfer_wizard

            clear_transfer_wizard(request.session)
            clear_realize_planned_wizard(request.session)
        _log_chat_exchange(
            db,
            user.id,
            request.session,
            "Confirmar",
            response,
            tool_used=tool_call.tool,
            source="confirmation",
            metadata={"pending_action": tool_call.model_dump()},
        )
        return templates.TemplateResponse(
            "partials/agent_response.html",
            {
                "request": request,
                "user": user,
                "user_message": "Confirmar",
                "agent_message": response,
                "needs_confirmation": False,
                "refresh_page": outcome["action"]
                in {
                    "register_expense",
                    "register_income",
                    "register_transfer",
                    "realize_planned",
                    "update_transfer",
                    "update_transaction",
                    "update_account",
                    "update_card",
                    "delete_card",
                    "delete_transaction",
                    "create_account",
                    "create_card",
                    "create_category",
                },
                "keep_chat_open": True,
            },
        )

    result = await process_message(
        db, user.id, message, session=request.session, confirmed=confirmed == "true"
    )
    from app.services.account_wizard import clear_wizard, get_wizard

    if result.clear_wizard:
        clear_wizard(request.session)

    metadata = {}
    if result.pending_action:
        metadata["pending_action"] = result.pending_action
    if result.needs_confirmation:
        metadata["needs_confirmation"] = True
    if get_wizard(request.session):
        metadata["wizard_active"] = True
    if get_transaction_wizard(request.session):
        metadata["transaction_wizard_active"] = True

    _log_chat_exchange(
        db,
        user.id,
        request.session,
        message,
        result.message,
        tool_used=result.tool_used,
        source=result.source,
        metadata=metadata or None,
    )

    return templates.TemplateResponse(
        "partials/agent_response.html",
        {
            "request": request,
            "user": user,
            "user_message": message,
            "agent_message": result.message,
            "needs_confirmation": result.needs_confirmation,
            "pending_action": result.pending_action,
            "suggestions": result.suggestions,
            "refresh_page": False,
        },
    )
