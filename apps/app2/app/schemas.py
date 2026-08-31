from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.text_correction import correct_category_name, correct_movement_description


def cents_to_decimal(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)


def format_brl(cents: int) -> str:
    negative = cents < 0
    cents = abs(cents)
    whole, frac = divmod(cents, 100)
    whole_str = f"{whole:,}".replace(",", ".")
    result = f"{whole_str},{frac:02d}"
    return f"-{result}" if negative else result


def decimal_to_cents(value: Decimal | str | float) -> int:
    if isinstance(value, str):
        raw = value.strip()
        if "," in raw and "." in raw:
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", ".")
        dec = Decimal(raw).quantize(Decimal("0.01"))
    else:
        dec = Decimal(str(value)).quantize(Decimal("0.01"))
    return int(dec * 100)


class TransactionCreate(BaseModel):
    account_id: int
    category_id: int | None = None
    type: Literal["expense", "income"]
    amount_cents: int = Field(gt=0)
    description: str = Field(min_length=1, max_length=255)
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None
    status: Literal["actual", "planned"] = "actual"

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str) -> str:
        return correct_movement_description(v)[:255]


class BudgetCreate(BaseModel):
    category_id: int
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    limit_cents: int = Field(gt=0)


class RegisterExpenseInput(BaseModel):
    amount: str
    description: str
    account_name: str | None = None
    category_name: str | None = None
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None
    status: Literal["actual", "planned"] = "actual"

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str) -> str:
        return correct_movement_description(v)[:255]

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        decimal_to_cents(v)
        return v


class RegisterIncomeInput(BaseModel):
    amount: str
    description: str
    account_name: str | None = None
    category_name: str | None = None
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None
    status: Literal["actual", "planned"] = "actual"

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str) -> str:
        return correct_movement_description(v)[:255]

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        decimal_to_cents(v)
        return v


class UpdateTransactionInput(BaseModel):
    transaction_id: int | None = None
    amount: str | None = None
    description: str | None = None
    account_name: str | None = None
    category_name: str | None = None
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return v
        return correct_movement_description(str(v))[:255]

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            decimal_to_cents(v)
        return v


class DeleteTransactionInput(BaseModel):
    transaction_id: int | None = None
    amount: str | None = None
    description: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            decimal_to_cents(v)
        return v


class RealizePlannedInput(BaseModel):
    planned_id: int | None = None
    description: str | None = None
    amount: str | None = None
    account_name: str | None = None
    category_name: str | None = None
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return v
        return correct_movement_description(str(v))[:255]

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            decimal_to_cents(v)
        return v


class ListTransactionsInput(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
    type: Literal["expense", "income", "transfer", "all"] = "all"


class RegisterTransferInput(BaseModel):
    amount: str
    from_account_name: str | None = None
    to_account_name: str | None = None
    description: str | None = None
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return None
        return correct_movement_description(str(v))[:255]

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        decimal_to_cents(v)
        return v


class SummaryInput(BaseModel):
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    period: Literal["day", "week", "month"] = "month"
    ref_date: date | None = None


class BudgetStatusInput(BaseModel):
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)


class CreateAccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    account_type: Literal["corrente", "poupanca", "carteira", "cartao"]
    institution: str | None = None
    opening_balance: str | None = None
    opening_balance_date: date | None = None

    @field_validator("opening_balance")
    @classmethod
    def validate_opening_balance(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            decimal_to_cents(v)
        return v


class CreateCategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: Literal["expense", "income"]
    keywords: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return correct_category_name(v)[:100]

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return None
        return str(v).strip()[:500]


class UpdateAccountInput(BaseModel):
    account_id: int | None = None
    account_name: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    institution: str | None = None
    account_type: Literal["corrente", "poupanca", "carteira", "cartao"] | None = None
    opening_balance: str | None = None
    opening_balance_date: date | None = None

    @field_validator("opening_balance")
    @classmethod
    def validate_opening_balance(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            decimal_to_cents(v)
        return v


class ToolCall(BaseModel):
    tool: Literal[
        "register_expense",
        "register_income",
        "register_transfer",
        "realize_planned",
        "update_transaction",
        "delete_transaction",
        "update_account",
        "list_transactions",
        "list_accounts",
        "list_categories",
        "get_summary",
        "get_budget_status",
        "categorize",
        "create_account",
        "create_category",
        "unsupported_action",
    ]
    arguments: dict


class AgentResponse(BaseModel):
    message: str
    tool_used: str | None = None
    data: dict | None = None
    needs_confirmation: bool = False
    pending_action: dict | None = None
    clear_wizard: bool = False
    source: str | None = None
    suggestions: list[str] | None = None
