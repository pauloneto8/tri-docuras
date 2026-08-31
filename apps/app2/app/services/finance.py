from datetime import date, datetime, timedelta
from decimal import Decimal
import calendar
from uuid import uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, joinedload

from app.models import Account, Budget, Category, RecurringRule, Transaction, User
from app.schemas import (
    BudgetCreate,
    BudgetStatusInput,
    CreateAccountInput,
    ListTransactionsInput,
    RegisterExpenseInput,
    RegisterIncomeInput,
    RegisterTransferInput,
    RealizePlannedInput,
    SummaryInput,
    TransactionCreate,
    UpdateAccountInput,
    UpdateTransactionInput,
    DeleteTransactionInput,
    decimal_to_cents,
    format_brl,
)
from app.timezone import local_today


DEFAULT_CATEGORIES = [
    ("Alimentação", "expense", "mercado,supermercado,restaurante,lanche,padaria,ifood"),
    ("Transporte", "expense", "uber,99,onibus,metro,combustivel,gasolina,estacionamento,moto,viagem,transporte,passagem,passagens,taxi,busao"),
    ("Moradia", "expense", "aluguel,condominio,luz,agua,internet,gas"),
    ("Saúde", "expense", "farmacia,medico,hospital,plano de saude"),
    ("Lazer", "expense", "cinema,streaming,netflix,spotify"),
    ("Educação", "expense", "curso,livro,escola,faculdade"),
    ("Salário", "income", "salario,pagamento,pro labore"),
    ("Investimentos", "income", "rendimento,dividendo,juros"),
    ("Outros", "expense", "outros,diversos"),
]


def seed_defaults(db: Session, user_id: int) -> None:
    has_category = db.scalar(
        select(func.count()).select_from(Category).where(Category.user_id == user_id)
    )
    if has_category == 0:
        for name, cat_type, keywords in DEFAULT_CATEGORIES:
            db.add(Category(user_id=user_id, name=name, type=cat_type, keywords=keywords))
    else:
        for name, cat_type, keywords in DEFAULT_CATEGORIES:
            category = db.scalar(
                select(Category).where(
                    Category.user_id == user_id,
                    Category.name == name,
                    Category.type == cat_type,
                )
            )
            if category and category.keywords != keywords:
                category.keywords = keywords
    db.commit()


def get_primary_account(db: Session, user_id: int) -> Account | None:
    return db.scalar(
        select(Account)
        .where(Account.user_id == user_id, Account.is_active.is_(True))
        .order_by(Account.created_at.asc(), Account.id.asc())
    )


def complete_onboarding(
    db: Session,
    user_id: int,
    *,
    name: str,
    opening_balance: str | None = None,
    opening_balance_date: date | None = None,
) -> Account:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("Usuário não encontrado.")
    if user.onboarding_completed:
        raise ValueError("Onboarding já concluído.")

    result = create_account(
        db,
        user_id,
        CreateAccountInput(
            name=name.strip(),
            account_type="carteira",
            opening_balance=opening_balance or "0",
            opening_balance_date=opening_balance_date,
        ),
    )
    user.onboarding_completed = True
    db.commit()
    account = db.get(Account, result["id"])
    if not account:
        raise ValueError("Conta não encontrada após criação.")
    return account


def resolve_account(db: Session, user_id: int, account_name: str | None) -> Account:
    """Resolve conta existente; não cria conta nem usa fallback silencioso."""
    if not account_name or not account_name.strip():
        raise ValueError("Conta não informada.")
    return resolve_account_for_transaction(db, user_id, account_name.strip())


def resolve_account_for_transaction(db: Session, user_id: int, account_name: str) -> Account:
    account = db.scalar(
        select(Account).where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            func.lower(Account.name) == account_name.lower(),
        )
    )
    if not account:
        raise ValueError(f"Conta '{account_name}' não encontrada.")
    return account


def get_or_create_account(db: Session, user_id: int, name: str) -> Account:
    account = db.scalar(
        select(Account).where(Account.user_id == user_id, Account.name == name)
    )
    if account:
        return account
    account = Account(user_id=user_id, name=name, account_type="corrente")
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def find_category_by_name(db: Session, user_id: int, name: str, tx_type: str) -> Category | None:
    return db.scalar(
        select(Category).where(
            Category.user_id == user_id,
            func.lower(Category.name) == name.lower(),
            Category.type == tx_type,
        )
    )


def categorize_by_keywords(
    db: Session, user_id: int, description: str, tx_type: str
) -> Category | None:
    category = suggest_category_by_keywords(db, user_id, description, tx_type)
    if category:
        return category
    return db.scalar(
        select(Category).where(
            Category.user_id == user_id,
            Category.name == "Outros",
            Category.type == tx_type,
        )
    )


def suggest_category_by_keywords(
    db: Session, user_id: int, description: str, tx_type: str
) -> Category | None:
    """Sugere categoria por keywords; não retorna 'Outros' como fallback."""
    normalized = description.lower().strip()
    categories = db.scalars(
        select(Category).where(Category.user_id == user_id, Category.type == tx_type)
    ).all()

    best: Category | None = None
    best_score = 0.0
    for category in categories:
        if category.name == "Outros" or not category.keywords:
            continue
        for keyword in category.keywords.split(","):
            keyword = keyword.strip().lower()
            if not keyword:
                continue
            if keyword in normalized:
                score = len(keyword) / max(len(normalized), 1)
                if score > best_score:
                    best_score = score
                    best = category
    return best


def resolve_transaction_dates(
    status: str,
    *,
    competence_date: date | None = None,
    due_date: date | None = None,
    payment_date: date | None = None,
    transaction_date: date | None = None,
) -> tuple[date, date, date | None, date]:
    """Resolve competence, due, payment and cash (transaction_date) dates."""
    today = local_today()
    legacy = transaction_date or today

    if status == "planned":
        if payment_date is not None:
            raise ValueError("Lançamento previsto não pode ter data de pagamento.")
        due = due_date or legacy
        comp = competence_date or due
        payment = None
        cash_date = due
    else:
        payment = payment_date or legacy
        due = due_date or payment
        comp = competence_date or due
        cash_date = payment

    return comp, due, payment, cash_date


def create_transaction(db: Session, user_id: int, data: TransactionCreate) -> Transaction:
    comp, due, payment, cash_date = resolve_transaction_dates(
        data.status,
        competence_date=data.competence_date,
        due_date=data.due_date,
        payment_date=data.payment_date,
        transaction_date=data.transaction_date,
    )
    tx = Transaction(
        user_id=user_id,
        account_id=data.account_id,
        category_id=data.category_id,
        type=data.type,
        amount_cents=data.amount_cents,
        description=data.description,
        competence_date=comp,
        due_date=due,
        payment_date=payment,
        transaction_date=cash_date,
        status=data.status,
        recurrence_id=data.recurrence_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def _register_recurring_movement(
    db: Session,
    user_id: int,
    *,
    account: Account,
    category: Category | None,
    tx_type: str,
    payload: RegisterExpenseInput | RegisterIncomeInput,
) -> dict:
    from app.services.recurrence import (
        create_recurring_rule,
        ensure_recurring_horizon,
        format_recurrence_label,
    )

    if not payload.frequency:
        raise ValueError("Frequência é obrigatória para lançamento fixo.")

    amount_cents = decimal_to_cents(payload.amount)
    start_date = (
        payload.competence_date
        or payload.due_date
        or payload.payment_date
        or payload.transaction_date
        or local_today()
    )

    rule = create_recurring_rule(
        db,
        user_id,
        account_id=account.id,
        category_id=category.id if category else None,
        tx_type=tx_type,
        amount_cents=amount_cents,
        description=payload.description,
        frequency=payload.frequency,
        start_date=start_date,
        end_date=payload.recurrence_end_date,
    )

    tx = create_transaction(
        db,
        user_id,
        TransactionCreate(
            account_id=account.id,
            category_id=category.id if category else None,
            type=tx_type,
            amount_cents=amount_cents,
            description=payload.description,
            competence_date=payload.competence_date or start_date,
            due_date=payload.due_date or start_date,
            payment_date=payload.payment_date,
            transaction_date=payload.transaction_date,
            status=payload.status,
            recurrence_id=rule.id,
        ),
    )
    ensure_recurring_horizon(db, user_id, rule_id=rule.id)
    result = format_transaction(tx)
    result["recurrence_id"] = rule.id
    result["frequency"] = rule.frequency
    result["recurrence_label"] = format_recurrence_label(rule.frequency)
    return result


def register_expense(db: Session, user_id: int, payload: RegisterExpenseInput) -> dict:
    if not payload.account_name or not payload.category_name:
        raise ValueError("Conta e categoria são obrigatórias para registrar a despesa.")
    account = resolve_account_for_transaction(db, user_id, payload.account_name)
    category = find_category_by_name(db, user_id, payload.category_name, "expense")
    if not category:
        raise ValueError(f"Categoria '{payload.category_name}' não encontrada.")

    if payload.frequency:
        return _register_recurring_movement(
            db, user_id, account=account, category=category, tx_type="expense", payload=payload
        )

    tx = create_transaction(
        db,
        user_id,
        TransactionCreate(
            account_id=account.id,
            category_id=category.id if category else None,
            type="expense",
            amount_cents=decimal_to_cents(payload.amount),
            description=payload.description,
            competence_date=payload.competence_date,
            due_date=payload.due_date,
            payment_date=payload.payment_date,
            transaction_date=payload.transaction_date,
            status=payload.status,
        ),
    )
    return format_transaction(tx)


def register_income(db: Session, user_id: int, payload: RegisterIncomeInput) -> dict:
    if not payload.account_name or not payload.category_name:
        raise ValueError("Conta e categoria são obrigatórias para registrar a receita.")
    account = resolve_account_for_transaction(db, user_id, payload.account_name)
    category = find_category_by_name(db, user_id, payload.category_name, "income")
    if not category:
        raise ValueError(f"Categoria '{payload.category_name}' não encontrada.")

    if payload.frequency:
        return _register_recurring_movement(
            db, user_id, account=account, category=category, tx_type="income", payload=payload
        )

    tx = create_transaction(
        db,
        user_id,
        TransactionCreate(
            account_id=account.id,
            category_id=category.id if category else None,
            type="income",
            amount_cents=decimal_to_cents(payload.amount),
            description=payload.description,
            competence_date=payload.competence_date,
            due_date=payload.due_date,
            payment_date=payload.payment_date,
            transaction_date=payload.transaction_date,
            status=payload.status,
        ),
    )
    return format_transaction(tx)


def create_user_transaction(
    db: Session,
    user_id: int,
    data: TransactionCreate,
    *,
    frequency: str | None = None,
    recurrence_end_date: date | None = None,
) -> dict:
    """Cria lançamento manual (formulário) com suporte opcional a recorrência."""
    if not frequency:
        tx = create_transaction(db, user_id, data)
        return format_transaction(tx)

    account = db.get(Account, data.account_id)
    if not account or account.user_id != user_id:
        raise ValueError("Conta inválida.")
    category = db.get(Category, data.category_id) if data.category_id else None

    if data.type == "expense":
        payload = RegisterExpenseInput(
            amount=format_brl(data.amount_cents),
            description=data.description,
            account_name=account.name,
            category_name=category.name if category else "Outros",
            competence_date=data.competence_date,
            due_date=data.due_date,
            payment_date=data.payment_date,
            transaction_date=data.transaction_date,
            status=data.status,
            frequency=frequency,  # type: ignore[arg-type]
            recurrence_end_date=recurrence_end_date,
        )
        return register_expense(db, user_id, payload)

    payload = RegisterIncomeInput(
        amount=format_brl(data.amount_cents),
        description=data.description,
        account_name=account.name,
        category_name=category.name if category else "Salário",
        competence_date=data.competence_date,
        due_date=data.due_date,
        payment_date=data.payment_date,
        transaction_date=data.transaction_date,
        status=data.status,
        frequency=frequency,  # type: ignore[arg-type]
        recurrence_end_date=recurrence_end_date,
    )
    return register_income(db, user_id, payload)


def realize_planned(db: Session, user_id: int, payload: RealizePlannedInput) -> dict:
    override_description = (
        payload.description.strip()[:255]
        if payload.description and payload.description.strip()
        else None
    )

    if payload.planned_id is not None:
        planned = find_transaction(db, user_id, transaction_id=payload.planned_id)
    elif override_description:
        candidates = find_transactions(
            db,
            user_id,
            description=override_description,
            limit=20,
        )
        planned = next((tx for tx in candidates if tx.status == "planned"), None)
        override_description = None
    else:
        raise ValueError("Informe o ID ou a descrição do lançamento previsto.")

    if not planned:
        raise ValueError("Lançamento previsto não encontrado.")
    if planned.status != "planned":
        raise ValueError("O lançamento informado não é um previsto.")
    if planned.type in {"transfer_out", "transfer_in"}:
        raise ValueError("Transferências não podem ser previstas.")

    existing = db.scalar(
        select(Transaction.id).where(
            Transaction.user_id == user_id,
            Transaction.source_planned_id == planned.id,
        )
    )
    if existing:
        raise ValueError("Este previsto já foi realizado.")

    account_name = payload.account_name
    if account_name and account_name.strip():
        account = resolve_account_for_transaction(db, user_id, account_name.strip())
    else:
        account = planned.account

    if account.id != planned.account_id:
        planned.account_id = account.id

    category = planned.category
    if payload.category_name and payload.category_name.strip():
        category = find_category_by_name(
            db, user_id, payload.category_name.strip(), planned.type
        )
        if not category:
            raise ValueError(f"Categoria '{payload.category_name}' não encontrada.")

    amount_cents = (
        decimal_to_cents(payload.amount)
        if payload.amount and payload.amount.strip()
        else planned.amount_cents
    )
    description = override_description or planned.description
    payment_date = payload.payment_date or payload.transaction_date or local_today()
    competence_date = payload.competence_date or planned.competence_date
    due_date = payload.due_date or planned.due_date
    comp, due, payment, cash_date = resolve_transaction_dates(
        "actual",
        competence_date=competence_date,
        due_date=due_date,
        payment_date=payment_date,
    )

    actual = Transaction(
        user_id=user_id,
        account_id=account.id,
        category_id=category.id if category else None,
        type=planned.type,
        amount_cents=amount_cents,
        description=description,
        competence_date=comp,
        due_date=due,
        payment_date=payment,
        transaction_date=cash_date,
        status="actual",
        source_planned_id=planned.id,
    )
    db.add(actual)
    db.commit()
    db.refresh(planned)
    db.refresh(actual)

    if planned.recurrence_id:
        from app.services.recurrence import ensure_recurring_horizon

        ensure_recurring_horizon(db, user_id, rule_id=planned.recurrence_id)

    return {
        "planned": format_transaction(planned),
        "actual": format_transaction(actual),
    }


def register_transfer(db: Session, user_id: int, payload: RegisterTransferInput) -> dict:
    if not payload.from_account_name or not payload.to_account_name:
        raise ValueError("Conta de origem e destino são obrigatórias para transferência.")
    from_account = resolve_account_for_transaction(db, user_id, payload.from_account_name)
    to_account = resolve_account_for_transaction(db, user_id, payload.to_account_name)
    if from_account.id == to_account.id:
        raise ValueError("A conta de origem e destino devem ser diferentes.")

    tx_date = payload.transaction_date or local_today()
    comp, due, payment, cash_date = resolve_transaction_dates(
        "actual",
        competence_date=payload.competence_date,
        due_date=payload.due_date,
        payment_date=payload.payment_date or tx_date,
        transaction_date=tx_date,
    )
    amount_cents = decimal_to_cents(payload.amount)
    description = payload.description or f"Transferência para {to_account.name}"
    group_id = str(uuid4())

    out_tx = Transaction(
        user_id=user_id,
        account_id=from_account.id,
        category_id=None,
        type="transfer_out",
        amount_cents=amount_cents,
        description=description,
        competence_date=comp,
        due_date=due,
        payment_date=payment,
        transaction_date=cash_date,
        transfer_group_id=group_id,
        counterparty_account_id=to_account.id,
        status="actual",
    )
    in_tx = Transaction(
        user_id=user_id,
        account_id=to_account.id,
        category_id=None,
        type="transfer_in",
        amount_cents=amount_cents,
        description=payload.description or f"Transferência de {from_account.name}",
        competence_date=comp,
        due_date=due,
        payment_date=payment,
        transaction_date=cash_date,
        transfer_group_id=group_id,
        counterparty_account_id=from_account.id,
        status="actual",
    )
    db.add(out_tx)
    db.add(in_tx)
    db.commit()
    db.refresh(out_tx)
    db.refresh(in_tx)
    return format_transfer(out_tx, in_tx, from_account.name, to_account.name)


def _get_transfer_pair(db: Session, user_id: int, tx: Transaction) -> list[Transaction]:
    if not tx.transfer_group_id:
        return [tx]
    return list(
        db.scalars(
            select(Transaction)
            .options(
                joinedload(Transaction.account),
                joinedload(Transaction.counterparty_account),
                joinedload(Transaction.category),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.transfer_group_id == tx.transfer_group_id,
            )
        ).all()
    )


def find_transactions(
    db: Session,
    user_id: int,
    *,
    transaction_id: int | None = None,
    description: str | None = None,
    amount: str | None = None,
    limit: int = 10,
) -> list[Transaction]:
    if transaction_id is not None:
        tx = db.scalar(
            select(Transaction)
            .options(
                joinedload(Transaction.account),
                joinedload(Transaction.category),
                joinedload(Transaction.counterparty_account),
            )
            .where(Transaction.id == transaction_id, Transaction.user_id == user_id)
        )
        return [tx] if tx else []

    stmt = (
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.counterparty_account),
        )
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    )
    if description and description.strip():
        normalized = description.strip().lower()
        stmt = stmt.where(func.lower(Transaction.description).contains(normalized))
    if amount and amount.strip():
        stmt = stmt.where(Transaction.amount_cents == decimal_to_cents(amount))

    return list(db.scalars(stmt.limit(limit)).all())


def find_transaction(
    db: Session,
    user_id: int,
    *,
    transaction_id: int | None = None,
    description: str | None = None,
    amount: str | None = None,
) -> Transaction | None:
    results = find_transactions(
        db,
        user_id,
        transaction_id=transaction_id,
        description=description,
        amount=amount,
        limit=1,
    )
    return results[0] if results else None


def update_transaction(db: Session, user_id: int, payload: UpdateTransactionInput) -> dict:
    if not any(
        [
            payload.transaction_id,
            payload.amount,
            payload.description,
            payload.account_name,
            payload.category_name,
            payload.transaction_date,
            payload.competence_date,
            payload.due_date,
            payload.payment_date,
        ]
    ):
        raise ValueError("Informe ao menos um campo para atualizar o lançamento.")

    lookup_description = None
    if payload.description and not payload.transaction_id:
        lookup_description = payload.description

    tx = find_transaction(
        db,
        user_id,
        transaction_id=payload.transaction_id,
        description=lookup_description,
        amount=payload.amount if not payload.transaction_id else None,
    )
    if not tx:
        raise ValueError("Lançamento não encontrado.")

    if payload.amount and payload.amount.strip():
        tx.amount_cents = decimal_to_cents(payload.amount)
    if payload.description and payload.description.strip():
        tx.description = payload.description.strip()[:255]
    if payload.account_name and payload.account_name.strip():
        account = resolve_account_for_transaction(db, user_id, payload.account_name.strip())
        tx.account_id = account.id
    if payload.category_name and payload.category_name.strip():
        if tx.type in {"transfer_out", "transfer_in"}:
            raise ValueError("Transferências não possuem categoria.")
        category = find_category_by_name(db, user_id, payload.category_name.strip(), tx.type)
        if not category:
            raise ValueError(f"Categoria '{payload.category_name}' não encontrada.")
        tx.category_id = category.id
    if payload.transaction_date or payload.competence_date or payload.due_date or payload.payment_date:
        comp, due, payment, cash_date = resolve_transaction_dates(
            tx.status,
            competence_date=payload.competence_date or tx.competence_date,
            due_date=payload.due_date or tx.due_date,
            payment_date=payload.payment_date or tx.payment_date,
            transaction_date=payload.transaction_date or tx.transaction_date,
        )
        tx.competence_date = comp
        tx.due_date = due
        tx.payment_date = payment
        tx.transaction_date = cash_date

    if tx.transfer_group_id:
        pair = _get_transfer_pair(db, user_id, tx)
        for leg in pair:
            if leg.id == tx.id:
                continue
            if payload.amount and payload.amount.strip():
                leg.amount_cents = tx.amount_cents
            if (
                payload.transaction_date
                or payload.competence_date
                or payload.due_date
                or payload.payment_date
            ):
                leg.competence_date = tx.competence_date
                leg.due_date = tx.due_date
                leg.payment_date = tx.payment_date
                leg.transaction_date = tx.transaction_date
            if payload.description and payload.description.strip():
                if leg.type == "transfer_out":
                    leg.description = tx.description
                else:
                    leg.description = (
                        payload.description.strip()[:255]
                        if payload.description
                        else f"Transferência de {leg.counterparty_account.name if leg.counterparty_account else 'origem'}"
                    )

    db.commit()
    db.refresh(tx)
    return format_transaction(tx)


def delete_transaction(db: Session, user_id: int, payload: DeleteTransactionInput) -> dict:
    if payload.transaction_id is None:
        raise ValueError("ID do lançamento é obrigatório para excluir.")

    tx = find_transaction(db, user_id, transaction_id=payload.transaction_id)
    if not tx:
        raise ValueError("Lançamento não encontrado.")

    if tx.type in {"transfer_out", "transfer_in"}:
        pair = _get_transfer_pair(db, user_id, tx)
        snapshots = [format_transaction(leg) for leg in pair]
        for leg in pair:
            db.delete(leg)
        db.commit()
        return snapshots[0] if len(snapshots) == 1 else {
            "deleted": snapshots,
            "transfer_group_id": tx.transfer_group_id,
        }

    snapshot = format_transaction(tx)
    db.delete(tx)
    db.commit()
    return snapshot


def list_transactions(
    db: Session, user_id: int | None, payload: ListTransactionsInput
) -> list[dict]:
    stmt = (
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.counterparty_account),
            joinedload(Transaction.user),
            joinedload(Transaction.recurrence),
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .limit(payload.limit)
    )
    if user_id is not None:
        stmt = stmt.where(Transaction.user_id == user_id)
    if payload.type != "all":
        if payload.type == "transfer":
            stmt = stmt.where(Transaction.type.in_(("transfer_out", "transfer_in")))
        else:
            stmt = stmt.where(Transaction.type == payload.type)
    if payload.status != "all":
        stmt = stmt.where(Transaction.status == payload.status)
    rows = db.scalars(stmt).unique().all()
    include_user = user_id is None
    planned_ids = [tx.id for tx in rows if tx.status == "planned"]
    realized_map: dict[int, int] = {}
    if planned_ids and user_id is not None:
        actual_rows = db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.source_planned_id.in_(planned_ids),
            )
        ).all()
        for actual in actual_rows:
            if actual.source_planned_id is not None:
                realized_map[actual.source_planned_id] = actual.id
    return [
        format_transaction(
            tx,
            include_user=include_user,
            realized_actual_id=realized_map.get(tx.id),
        )
        for tx in rows
    ]


def _resolve_ref_date(payload: SummaryInput) -> date:
    if payload.ref_date:
        return payload.ref_date
    today = local_today()
    year = payload.year or today.year
    month = payload.month or today.month
    return date(year, month, 1)


def resolve_period_bounds(period: str, ref_date: date) -> tuple[date, date]:
    if period == "day":
        return ref_date, ref_date
    if period == "week":
        start = ref_date - timedelta(days=ref_date.weekday())
        return start, start + timedelta(days=6)
    start = ref_date.replace(day=1)
    _, last_day = calendar.monthrange(ref_date.year, ref_date.month)
    return start, ref_date.replace(day=last_day)


def shift_ref_date(period: str, ref_date: date, delta: int) -> date:
    if period == "day":
        return ref_date + timedelta(days=delta)
    if period == "week":
        return ref_date + timedelta(weeks=delta)
    month = ref_date.month + delta
    year = ref_date.year
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return date(year, month, 1)


def _period_labels(period: str, period_start: date, period_end: date) -> tuple[str, str]:
    if period == "day":
        period_label = period_start.strftime("%d/%m/%Y")
        previous_label = "Até o dia anterior"
        return period_label, previous_label
    if period == "week":
        period_label = (
            f"{period_start.strftime('%d/%m')} — {period_end.strftime('%d/%m/%Y')}"
        )
        previous_label = "Até o fim da semana anterior"
        return period_label, previous_label
    months = (
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    )
    period_label = f"{months[period_start.month - 1]}/{period_start.year}"
    if period_start.month == 1:
        previous_label = f"Até dezembro/{period_start.year - 1}"
    else:
        previous_label = f"Até {months[period_start.month - 2].lower()}/{period_start.year}"
    return period_label, previous_label


def _resolve_opening_balance_date(
    opening_cents: int, opening_balance_date: date | None
) -> date | None:
    if opening_balance_date is not None:
        return opening_balance_date
    if opening_cents <= 0:
        return None
    return local_today()


def _account_balance_at(db: Session, account: Account, as_of: date) -> int:
    opening_date = account.opening_balance_date
    opening_cents = int(account.opening_balance_cents or 0)

    if opening_date is not None:
        if as_of < opening_date:
            return 0
        opening = opening_cents
        tx_start = opening_date
    else:
        opening = opening_cents
        tx_start = None

    tx_filters = [
        Transaction.user_id == account.user_id,
        Transaction.account_id == account.id,
        Transaction.transaction_date <= as_of,
        Transaction.status == "actual",
    ]
    if tx_start is not None:
        tx_filters.append(Transaction.transaction_date >= tx_start)

    income = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            *tx_filters,
            Transaction.type.in_(("income", "transfer_in")),
        )
    )
    expense = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            *tx_filters,
            Transaction.type.in_(("expense", "transfer_out")),
        )
    )
    return opening + int(income or 0) - int(expense or 0)


def _sum_account_balances_as_of(
    db: Session, user_id: int | None, as_of: date
) -> int:
    stmt = select(Account).where(Account.is_active.is_(True))
    if user_id is not None:
        stmt = stmt.where(Account.user_id == user_id)
    accounts = db.scalars(stmt).all()
    return sum(_account_balance_at(db, account, as_of) for account in accounts)


def _sum_transactions(
    db: Session,
    user_id: int | None,
    tx_type: str,
    *,
    start: date | None = None,
    end: date | None = None,
    before: date | None = None,
    status: str = "actual",
) -> int:
    stmt = (
        select(func.coalesce(func.sum(Transaction.amount_cents), 0))
        .select_from(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Transaction.type == tx_type, Transaction.status == status)
    )
    if user_id is not None:
        stmt = stmt.where(Transaction.user_id == user_id)
    stmt = stmt.where(
        or_(
            Account.opening_balance_date.is_(None),
            Transaction.transaction_date >= Account.opening_balance_date,
        )
    )
    if before is not None:
        stmt = stmt.where(Transaction.transaction_date < before)
    if start is not None:
        stmt = stmt.where(Transaction.transaction_date >= start)
    if end is not None:
        stmt = stmt.where(Transaction.transaction_date <= end)
    return int(db.scalar(stmt) or 0)


def _realized_planned_ids_subquery(user_id: int | None):
    stmt = select(Transaction.source_planned_id).where(
        Transaction.source_planned_id.isnot(None),
        Transaction.status == "actual",
    )
    if user_id is not None:
        stmt = stmt.where(Transaction.user_id == user_id)
    return stmt.distinct()


def _sum_unrealized_planned(
    db: Session,
    user_id: int | None,
    tx_type: str,
    *,
    start: date,
    end: date,
) -> int:
    realized_ids = _realized_planned_ids_subquery(user_id)
    stmt = (
        select(func.coalesce(func.sum(Transaction.amount_cents), 0))
        .select_from(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Transaction.type == tx_type,
            Transaction.status == "planned",
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
            Transaction.id.not_in(realized_ids),
        )
    )
    if user_id is not None:
        stmt = stmt.where(Transaction.user_id == user_id)
    stmt = stmt.where(
        or_(
            Account.opening_balance_date.is_(None),
            Transaction.transaction_date >= Account.opening_balance_date,
        )
    )
    return int(db.scalar(stmt) or 0)


def _plan_vs_actual_pairs(
    db: Session, user_id: int | None, period_start: date, period_end: date
) -> list[dict]:
    stmt = (
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.source_planned),
        )
        .where(
            Transaction.status == "actual",
            Transaction.source_planned_id.isnot(None),
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    )
    if user_id is not None:
        stmt = stmt.where(Transaction.user_id == user_id)

    pairs: list[dict] = []
    for actual in db.scalars(stmt).unique().all():
        planned = actual.source_planned
        if not planned:
            planned = db.get(Transaction, actual.source_planned_id)
        if not planned:
            continue
        diff = actual.amount_cents - planned.amount_cents
        pairs.append(
            {
                "planned_id": planned.id,
                "actual_id": actual.id,
                "description": planned.description,
                "type": planned.type,
                "type_label": TRANSACTION_TYPE_LABELS.get(planned.type, planned.type),
                "planned_date": planned.due_date.isoformat(),
                "actual_date": actual.payment_date.isoformat() if actual.payment_date else actual.transaction_date.isoformat(),
                "planned_due_date": planned.due_date.isoformat(),
                "actual_payment_date": (
                    actual.payment_date.isoformat()
                    if actual.payment_date
                    else actual.transaction_date.isoformat()
                ),
                "planned_amount_cents": planned.amount_cents,
                "actual_amount_cents": actual.amount_cents,
                "difference_cents": diff,
                "planned_amount": format_brl(planned.amount_cents),
                "actual_amount": format_brl(actual.amount_cents),
                "difference": format_brl(diff),
            }
        )
    return pairs


def get_summary(db: Session, user_id: int | None, payload: SummaryInput) -> dict:
    ref_date = _resolve_ref_date(payload)
    period = payload.period or "month"
    period_start, period_end = resolve_period_bounds(period, ref_date)
    period_label, previous_label = _period_labels(period, period_start, period_end)

    previous_as_of = period_start - timedelta(days=1)
    previous_balance_cents = _sum_account_balances_as_of(db, user_id, previous_as_of)

    income = _sum_transactions(
        db, user_id, "income", start=period_start, end=period_end
    )
    expense = _sum_transactions(
        db, user_id, "expense", start=period_start, end=period_end
    )
    period_result_cents = income - expense
    ending_balance_cents = _sum_account_balances_as_of(db, user_id, period_end)

    total_balance_cents = _sum_account_balances_as_of(db, user_id, local_today())

    planned_income = _sum_transactions(
        db, user_id, "income", start=period_start, end=period_end, status="planned"
    )
    planned_expense = _sum_transactions(
        db, user_id, "expense", start=period_start, end=period_end, status="planned"
    )
    planned_result_cents = planned_income - planned_expense

    pending_planned_income = _sum_unrealized_planned(
        db, user_id, "income", start=period_start, end=period_end
    )
    pending_planned_expense = _sum_unrealized_planned(
        db, user_id, "expense", start=period_start, end=period_end
    )
    pending_planned_result_cents = pending_planned_income - pending_planned_expense

    # Projeção: saldo realizado ao fim do período + previstos ainda pendentes.
    projected_ending_balance_cents = (
        ending_balance_cents + pending_planned_income - pending_planned_expense
    )

    plan_vs_actual = _plan_vs_actual_pairs(db, user_id, period_start, period_end)

    return {
        "period": period,
        "ref_date": ref_date.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_label": period_label,
        "previous_label": previous_label,
        "year": period_start.year,
        "month": period_start.month,
        "income_cents": income,
        "expense_cents": expense,
        "balance_cents": period_result_cents,
        "income": format_brl(income),
        "expense": format_brl(expense),
        "balance": format_brl(period_result_cents),
        "previous_balance_cents": previous_balance_cents,
        "previous_balance": format_brl(previous_balance_cents),
        "ending_balance_cents": ending_balance_cents,
        "ending_balance": format_brl(ending_balance_cents),
        "total_balance_cents": total_balance_cents,
        "total_balance": format_brl(total_balance_cents),
        "planned_income_cents": planned_income,
        "planned_expense_cents": planned_expense,
        "planned_result_cents": planned_result_cents,
        "planned_income": format_brl(planned_income),
        "planned_expense": format_brl(planned_expense),
        "planned_result": format_brl(planned_result_cents),
        "pending_planned_income_cents": pending_planned_income,
        "pending_planned_expense_cents": pending_planned_expense,
        "pending_planned_result_cents": pending_planned_result_cents,
        "pending_planned_income": format_brl(pending_planned_income),
        "pending_planned_expense": format_brl(pending_planned_expense),
        "pending_planned_result": format_brl(pending_planned_result_cents),
        "projected_ending_balance_cents": projected_ending_balance_cents,
        "projected_ending_balance": format_brl(projected_ending_balance_cents),
        "plan_vs_actual": plan_vs_actual,
    }


def get_budget_status(
    db: Session, user_id: int | None, payload: BudgetStatusInput
) -> list[dict]:
    today = local_today()
    year = payload.year or today.year
    month = payload.month or today.month

    stmt = select(Budget).where(Budget.year == year, Budget.month == month)
    if user_id is not None:
        stmt = stmt.where(Budget.user_id == user_id)
    budgets = db.scalars(stmt.options(joinedload(Budget.category), joinedload(Budget.user))).unique().all()
    results = []
    for budget in budgets:
        spent_stmt = select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.category_id == budget.category_id,
            Transaction.type == "expense",
            Transaction.status == "actual",
            func.extract("year", Transaction.competence_date) == year,
            func.extract("month", Transaction.competence_date) == month,
        )
        if user_id is not None:
            spent_stmt = spent_stmt.where(Transaction.user_id == user_id)
        else:
            spent_stmt = spent_stmt.where(Transaction.user_id == budget.user_id)
        spent = db.scalar(spent_stmt)
        spent = int(spent or 0)
        limit = budget.limit_cents
        item = {
            "category": budget.category.name,
            "limit_cents": limit,
            "spent_cents": spent,
            "remaining_cents": limit - spent,
            "limit": format_brl(limit),
            "spent": format_brl(spent),
            "remaining": format_brl(limit - spent),
            "percent_used": round((spent / limit) * 100, 1) if limit else 0,
        }
        if user_id is None and budget.user:
            item["user_name"] = budget.user.name
            item["user_email"] = budget.user.email
        results.append(item)
    return results


def create_budget(db: Session, user_id: int, payload: BudgetCreate) -> dict:
    budget = Budget(user_id=user_id, **payload.model_dump())
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return {
        "id": budget.id,
        "category": budget.category.name,
        "year": budget.year,
        "month": budget.month,
        "limit": format_brl(budget.limit_cents),
    }


def find_account(
    db: Session,
    user_id: int,
    *,
    account_id: int | None = None,
    account_name: str | None = None,
) -> Account | None:
    if account_id is not None:
        return db.scalar(
            select(Account).where(
                Account.id == account_id,
                Account.user_id == user_id,
                Account.is_active.is_(True),
            )
        )

    if not account_name or not account_name.strip():
        return None

    normalized = account_name.strip()
    account = db.scalar(
        select(Account).where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            func.lower(Account.name) == normalized.lower(),
        )
    )
    if account:
        return account

    return db.scalar(
        select(Account).where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            func.lower(Account.name).contains(normalized.lower()),
        )
    )


def update_account(db: Session, user_id: int, payload: UpdateAccountInput) -> dict:
    if not any(
        [
            payload.name,
            payload.institution,
            payload.account_type,
            payload.opening_balance,
            payload.opening_balance_date,
        ]
    ):
        raise ValueError("Informe ao menos um campo para atualizar a conta.")

    account = find_account(
        db,
        user_id,
        account_id=payload.account_id,
        account_name=payload.account_name,
    )
    if not account:
        raise ValueError("Conta não encontrada.")

    if payload.name and payload.name.strip():
        new_name = payload.name.strip()
        duplicate = db.scalar(
            select(Account).where(
                Account.user_id == user_id,
                func.lower(Account.name) == new_name.lower(),
                Account.id != account.id,
            )
        )
        if duplicate:
            raise ValueError(f"Já existe uma conta com o nome '{new_name}'.")
        account.name = new_name

    if payload.institution is not None:
        account.institution = payload.institution.strip() or None

    if payload.account_type:
        account.account_type = payload.account_type

    if payload.opening_balance is not None and payload.opening_balance.strip():
        opening_cents = decimal_to_cents(payload.opening_balance)
        account.opening_balance_cents = opening_cents
        account.opening_balance_date = _resolve_opening_balance_date(
            opening_cents, payload.opening_balance_date
        )
    elif payload.opening_balance_date is not None:
        account.opening_balance_date = payload.opening_balance_date

    db.commit()
    db.refresh(account)
    return format_account(account)


def create_account(db: Session, user_id: int, payload: CreateAccountInput) -> dict:
    existing = db.scalar(
        select(Account).where(Account.user_id == user_id, Account.name == payload.name)
    )
    if existing:
        raise ValueError(f"Já existe uma conta com o nome '{payload.name}'.")

    opening_cents = 0
    if payload.opening_balance and payload.opening_balance.strip():
        opening_cents = decimal_to_cents(payload.opening_balance)
    opening_date = _resolve_opening_balance_date(
        opening_cents, payload.opening_balance_date
    )

    account = Account(
        user_id=user_id,
        name=payload.name.strip(),
        institution=payload.institution.strip() if payload.institution else None,
        account_type=payload.account_type,
        opening_balance_cents=opening_cents,
        opening_balance_date=opening_date,
        description=payload.institution,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return format_account(account)


def create_category(db: Session, user_id: int, payload) -> dict:
    from app.schemas import CreateCategoryInput

    if not isinstance(payload, CreateCategoryInput):
        payload = CreateCategoryInput(**payload)

    existing = db.scalar(
        select(Category).where(
            Category.user_id == user_id,
            func.lower(Category.name) == payload.name.lower(),
        )
    )
    if existing:
        raise ValueError(f"Já existe a categoria '{payload.name}'.")

    category = Category(
        user_id=user_id,
        name=payload.name.strip(),
        type=payload.type,
        keywords=payload.keywords,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return format_category(category)


def list_user_categories(db: Session, user_id: int) -> list[dict]:
    categories = db.scalars(
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(Category.type.asc(), Category.name.asc())
    ).all()
    return [format_category(c) for c in categories]


def format_category(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "type": category.type,
        "type_label": "Despesa" if category.type == "expense" else "Receita",
        "keywords": category.keywords,
    }


ACCOUNT_TYPE_LABELS = {
    "corrente": "Corrente",
    "poupanca": "Poupança",
    "carteira": "Carteira",
    "cartao": "Cartão",
}

TRANSACTION_TYPE_LABELS = {
    "expense": "Despesa",
    "income": "Receita",
    "transfer_out": "Transferência (saída)",
    "transfer_in": "Transferência (entrada)",
}

TRANSACTION_STATUS_LABELS = {
    "actual": "Realizado",
    "planned": "Previsto",
}


def format_transfer(
    out_tx: Transaction,
    in_tx: Transaction,
    from_name: str,
    to_name: str,
) -> dict:
    return {
        "transfer_group_id": out_tx.transfer_group_id,
        "amount_cents": out_tx.amount_cents,
        "amount": format_brl(out_tx.amount_cents),
        "from_account": from_name,
        "to_account": to_name,
        "description": out_tx.description,
        "transaction_date": out_tx.transaction_date.isoformat(),
        "out_id": out_tx.id,
        "in_id": in_tx.id,
    }


def format_account(account: Account) -> dict:
    return {
        "id": account.id,
        "name": account.name,
        "institution": account.institution,
        "account_type": account.account_type,
        "account_type_label": ACCOUNT_TYPE_LABELS.get(account.account_type, account.account_type),
        "opening_balance": format_brl(account.opening_balance_cents),
        "opening_balance_cents": account.opening_balance_cents,
        "opening_balance_date": (
            account.opening_balance_date.isoformat()
            if account.opening_balance_date
            else None
        ),
        "opening_balance_date_label": (
            account.opening_balance_date.strftime("%d/%m/%Y")
            if account.opening_balance_date
            else None
        ),
    }


def format_transaction(
    tx: Transaction,
    *,
    include_user: bool = False,
    realized_actual_id: int | None = None,
) -> dict:
    from app.services.recurrence import format_recurrence_label

    counterparty = None
    if tx.counterparty_account:
        counterparty = tx.counterparty_account.name
    elif tx.counterparty_account_id:
        counterparty = getattr(tx, "_counterparty_name", None)

    status = tx.status or "actual"
    data = {
        "id": tx.id,
        "type": tx.type,
        "type_label": TRANSACTION_TYPE_LABELS.get(tx.type, tx.type),
        "status": status,
        "status_label": TRANSACTION_STATUS_LABELS.get(status, status),
        "amount_cents": tx.amount_cents,
        "amount": format_brl(tx.amount_cents),
        "description": tx.description,
        "transaction_date": tx.transaction_date.isoformat(),
        "competence_date": tx.competence_date.isoformat(),
        "due_date": tx.due_date.isoformat(),
        "payment_date": tx.payment_date.isoformat() if tx.payment_date else None,
        "competence_date_label": tx.competence_date.strftime("%d/%m/%Y"),
        "due_date_label": tx.due_date.strftime("%d/%m/%Y"),
        "payment_date_label": (
            tx.payment_date.strftime("%d/%m/%Y") if tx.payment_date else None
        ),
        "account": tx.account.name if tx.account else None,
        "category": tx.category.name if tx.category else None,
        "transfer_group_id": tx.transfer_group_id,
        "counterparty_account": counterparty,
        "source_planned_id": tx.source_planned_id,
        "recurrence_id": tx.recurrence_id,
        "frequency": tx.recurrence.frequency if tx.recurrence else None,
        "recurrence_label": (
            format_recurrence_label(tx.recurrence.frequency) if tx.recurrence else None
        ),
        "is_realized": status == "planned" and realized_actual_id is not None,
        "realized_actual_id": realized_actual_id,
        "created_at": tx.created_at.isoformat() if isinstance(tx.created_at, datetime) else None,
    }
    if include_user and tx.user:
        data["user_name"] = tx.user.name
        data["user_email"] = tx.user.email
    return data


def account_balances(
    db: Session, user_id: int | None, *, as_of: date | None = None
) -> list[dict]:
    stmt = select(Account).where(Account.is_active.is_(True))
    if user_id is not None:
        stmt = stmt.where(Account.user_id == user_id)
    accounts = db.scalars(stmt.options(joinedload(Account.user))).unique().all()
    results = []
    balance_date = as_of or local_today()
    for account in accounts:
        balance = _account_balance_at(db, account, balance_date)
        opening = int(account.opening_balance_cents or 0)
        item = {
            "id": account.id,
            "account": account.name,
            "institution": account.institution,
            "account_type": account.account_type,
            "account_type_label": ACCOUNT_TYPE_LABELS.get(
                account.account_type, account.account_type
            ),
            "opening_balance": format_brl(opening),
            "opening_balance_date": (
                account.opening_balance_date.isoformat()
                if account.opening_balance_date
                else None
            ),
            "opening_balance_date_label": (
                account.opening_balance_date.strftime("%d/%m/%Y")
                if account.opening_balance_date
                else None
            ),
            "balance_cents": balance,
            "balance": format_brl(balance),
        }
        if user_id is None and account.user:
            item["user_name"] = account.user.name
            item["user_email"] = account.user.email
        results.append(item)
    return results


def deactivate_account(db: Session, user_id: int, account_id: int) -> None:
    account = db.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.is_active.is_(True),
        )
    )
    if not account:
        raise ValueError("Conta não encontrada.")

    active_count = db.scalar(
        select(func.count()).select_from(Account).where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
        )
    )
    if active_count <= 1:
        raise ValueError("Não é possível desativar a única conta ativa.")

    account.is_active = False
    db.commit()
