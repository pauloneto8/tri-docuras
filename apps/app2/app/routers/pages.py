from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.agent.runner import process_message
from app.auth import read_scope_id, require_root, require_user
from app.db import get_db
from app.models import Account, Category, User
from app.security.csrf import ensure_csrf_token, validate_csrf_token
from app.schemas import (
    BudgetCreate,
    BudgetStatusInput,
    CreateAccountInput,
    ListTransactionsInput,
    RealizePlannedInput,
    SummaryInput,
    ToolCall,
    TransactionCreate,
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
    balances = finance.account_balances(db, scope, as_of=period_end)
    recent = finance.list_transactions(db, scope, ListTransactionsInput(limit=5))
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


def _transactions_page_context(
    request: Request,
    user: User,
    db: Session,
    *,
    success: str | None = None,
) -> dict:
    scope = read_scope_id(user)
    finance.seed_defaults(db, user.id)
    planned = finance.list_transactions(
        db, scope, ListTransactionsInput(limit=50, status="planned")
    )
    pending_transactions = [tx for tx in planned if not tx["is_realized"]]
    actual_transactions = finance.list_transactions(
        db, scope, ListTransactionsInput(limit=50, status="actual")
    )
    categories = (
        db.query(Category)
        .filter(Category.user_id == user.id)
        .order_by(Category.name)
        .all()
    )
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user.id, Account.is_active.is_(True))
        .order_by(Account.name)
        .all()
    )
    return {
        "request": request,
        "user": user,
        "is_root": user.is_root,
        "pending_transactions": pending_transactions,
        "actual_transactions": actual_transactions,
        "categories": categories,
        "accounts": accounts,
        "success": success,
        "today": local_today().isoformat(),
    }


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    return templates.TemplateResponse(
        "transactions.html",
        _transactions_page_context(request, user, db),
    )


@router.get("/accounts", response_class=HTMLResponse)
async def accounts_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    scope = read_scope_id(user)
    finance.seed_defaults(db, user.id)
    accounts = finance.account_balances(db, scope)
    return templates.TemplateResponse(
        "accounts.html",
        {
            "request": request,
            "user": user,
            "is_root": user.is_root,
            "accounts": accounts,
            "today": local_today().isoformat(),
        },
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
    scope = read_scope_id(user)
    error = None
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
                account_type=account_type,
                institution=institution or None,
                opening_balance=opening_balance or None,
                opening_balance_date=balance_date,
            ),
        )
        accounts = finance.account_balances(db, scope)
        return templates.TemplateResponse(
            "accounts.html",
            {
                "request": request,
                "user": user,
                "is_root": user.is_root,
                "accounts": accounts,
                "success": "Conta cadastrada com sucesso.",
                "today": local_today().isoformat(),
            },
        )
    except ValueError as exc:
        error = str(exc)
        accounts = finance.account_balances(db, scope)
        return templates.TemplateResponse(
            "accounts.html",
            {
                "request": request,
                "user": user,
                "is_root": user.is_root,
                "accounts": accounts,
                "error": error,
                "today": local_today().isoformat(),
            },
        )


@router.post("/accounts/deactivate", response_class=HTMLResponse)
async def deactivate_account_form(
    request: Request,
    account_id: int = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    scope = read_scope_id(user)
    error = None
    try:
        finance.deactivate_account(db, user.id, account_id)
        success = "Conta desativada com sucesso."
    except ValueError as exc:
        error = str(exc)
        success = None
    accounts = finance.account_balances(db, scope)
    return templates.TemplateResponse(
        "accounts.html",
        {
            "request": request,
            "user": user,
            "is_root": user.is_root,
            "accounts": accounts,
            "success": success,
            "error": error,
            "today": local_today().isoformat(),
        },
    )


@router.post("/transactions", response_class=HTMLResponse)
async def create_transaction_form(
    request: Request,
    account_id: int | None = Form(None),
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
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)

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
        if account_id is None:
            raise ValueError("Conta é obrigatória.")
        planned = is_planned == "on"
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
        finance.create_transaction(
            db,
            user.id,
            TransactionCreate(
                account_id=account_id,
                category_id=category_id or None,
                type=type,
                amount_cents=decimal_to_cents(amount),
                description=description or "Lançamento",
                competence_date=comp,
                due_date=due,
                payment_date=pay,
                status="planned" if planned else "actual",
            ),
        )
        success = (
            "Previsão registrada com sucesso."
            if planned
            else "Transação registrada com sucesso."
        )
    return templates.TemplateResponse(
        "transactions.html",
        _transactions_page_context(request, user, db, success=success),
    )


@router.post("/transactions/{planned_id}/realize", response_class=HTMLResponse)
async def realize_planned_form(
    planned_id: int,
    request: Request,
    amount: str | None = Form(None),
    payment_date: date = Form(...),
    description: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    finance.realize_planned(
        db,
        user.id,
        RealizePlannedInput(
            planned_id=planned_id,
            amount=amount if amount and amount.strip() else None,
            payment_date=payment_date,
            description=description or None,
        ),
    )
    return templates.TemplateResponse(
        "transactions.html",
        _transactions_page_context(
            request, user, db, success="Previsto realizado com sucesso."
        ),
    )


@router.get("/budgets", response_class=HTMLResponse)
async def budgets_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    templates = get_templates(request)
    scope = read_scope_id(user)
    finance.seed_defaults(db, user.id)
    budgets = finance.get_budget_status(db, scope, BudgetStatusInput())
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
            "today": local_today(),
        },
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
    scope = read_scope_id(user)
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
    budgets = finance.get_budget_status(db, scope, BudgetStatusInput())
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
            "today": local_today(),
            "success": "Orçamento definido com sucesso.",
        },
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

    if is_cancel_message(message) and confirmed != "true":
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
                    "user_message": "Confirmar",
                    "agent_message": response,
                    "needs_confirmation": False,
                    "refresh_page": True,
                    "keep_chat_open": True,
                },
            )

        tool_call = ToolCall(**parsed_action)
        outcome = execute_tool(db, user.id, tool_call)
        response = format_tool_result(outcome["action"], outcome["result"])
        if tool_call.tool == "create_account":
            clear_wizard(request.session)
        if tool_call.tool == "create_category":
            clear_category_wizard(request.session)
        if tool_call.tool in {"register_expense", "register_income", "register_transfer", "realize_planned", "update_transaction", "update_account", "delete_transaction"}:
            clear_transaction_wizard(request.session)
            from app.services.transfer_slots import clear_wizard as clear_transfer_wizard

            clear_transfer_wizard(request.session)
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
                "user_message": "Confirmar",
                "agent_message": response,
                "needs_confirmation": False,
                "refresh_page": outcome["action"]
                in {
                    "register_expense",
                    "register_income",
                    "register_transfer",
                    "realize_planned",
                    "update_transaction",
                    "update_account",
                    "delete_transaction",
                    "create_account",
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
            "user_message": message,
            "agent_message": result.message,
            "needs_confirmation": result.needs_confirmation,
            "pending_action": result.pending_action,
            "suggestions": result.suggestions,
            "refresh_page": False,
        },
    )
