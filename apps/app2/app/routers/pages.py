from datetime import date

from fastapi import APIRouter, Depends, Form, Request
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


def _transactions_page_context(
    request: Request,
    user: User,
    db: Session,
    *,
    success: str | None = None,
    error: str | None = None,
    period: str | None = None,
    ref_date: str | None = None,
) -> dict:
    scope = read_scope_id(user)
    finance.seed_defaults(db, user.id)
    from app.services.recurrence import ensure_recurring_horizon

    ensure_recurring_horizon(db, scope)

    period_param = period if period is not None else request.query_params.get("period")
    ref_param = ref_date if ref_date is not None else request.query_params.get("ref_date")
    period, current_ref, period_start, period_end, period_label = (
        _parse_transactions_period(period_param, ref_param)
    )
    prev_ref = finance.shift_ref_date(period, current_ref, -1)
    next_ref = finance.shift_ref_date(period, current_ref, 1)

    list_filter = dict(
        limit=100,
        start_date=period_start,
        end_date=period_end,
    )
    planned = finance.list_transactions(
        db, scope, ListTransactionsInput(status="planned", **list_filter)
    )
    pending_transactions = [tx for tx in planned if not tx["is_realized"]]
    actual_transactions = [
        tx
        for tx in finance.list_transactions(
            db, scope, ListTransactionsInput(status="actual", **list_filter)
        )
        if not tx.get("card") and tx.get("type") != "transfer_in"
    ]
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
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "pending_transactions": pending_transactions,
        "actual_transactions": actual_transactions,
        "accounts": accounts,
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
    period: str = "month",
    ref_date: str | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    return templates.TemplateResponse(
        "transactions.html",
        _transactions_page_context(
            request, user, db, period=period, ref_date=ref_date
        ),
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
    from app.services.credit_cards import list_credit_cards, list_invoices, sync_credit_cards

    finance.seed_defaults(db, user.id)
    sync_credit_cards(db, user.id)
    bank_accounts = finance.account_balances(db, scope)
    credit_cards = list_credit_cards(db, user.id)
    invoices = list_invoices(db, user.id, limit=20)
    flash_success, flash_error = _consume_flash(request, success=success, error=error)
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "accounts": credit_cards if focus_cards else bank_accounts,
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
    account_id: int | None = Form(None),
    card_id: int | None = Form(None),
    from_account_id: int | None = Form(None),
    to_account_id: int | None = Form(None),
    category_id: int | None = Form(None),
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
    installment_count: int | None = Form(None),
    installment_interval: str | None = Form(None),
    installment_amount_basis: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)

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
                    category_id=category_id or None,
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
    account_id: int | None = Form(None),
    category_id: int | None = Form(None),
    from_account_id: int | None = Form(None),
    to_account_id: int | None = Form(None),
    competence_date: str | None = Form(None),
    due_date: str | None = Form(None),
    payment_date: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
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
            category = db.get(Category, category_id) if category_id else None
            if category_id and (not category or category.user_id != user.id):
                raise ValueError("Categoria inválida.")
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
                    competence_date=comp,
                    due_date=due,
                    payment_date=pay,
                ),
            )
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
    templates = get_templates(request)
    users = admin.list_users_overview(db)
    summary = finance.get_summary(db, None, SummaryInput())
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "is_root": True,
            "users": users,
            "summary": summary,
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
        if tool_call.tool == "create_account":
            clear_wizard(request.session)
        if tool_call.tool == "create_card":
            from app.services.card_wizard import clear_wizard as clear_card_wizard

            clear_card_wizard(request.session)
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
