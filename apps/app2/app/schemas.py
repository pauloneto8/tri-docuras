from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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
    account_id: int | None = None
    card_id: int | None = None
    category_id: int | None = None
    type: Literal["expense", "income"]
    amount_cents: int = Field(gt=0)
    description: str = Field(min_length=1, max_length=255)
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None
    status: Literal["actual", "planned"] = "actual"
    recurrence_id: int | None = None
    installment_plan_id: int | None = None
    installment_index: int | None = None
    invoice_id: int | None = None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str) -> str:
        return correct_movement_description(v)[:255]

    @model_validator(mode="after")
    def validate_account_or_card(self):
        if self.account_id is None and self.card_id is None:
            raise ValueError("Informe a conta ou o cartão do lançamento.")
        return self


class BudgetCreate(BaseModel):
    category_id: int
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    limit_cents: int = Field(gt=0)


class RegisterExpenseInput(BaseModel):
    amount: str
    description: str
    account_name: str | None = None
    card_name: str | None = None
    category_name: str | None = None
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None
    status: Literal["actual", "planned"] = "actual"
    frequency: Literal["daily", "weekly", "monthly"] | None = None
    recurrence_end_date: date | None = None
    installment_count: int | None = Field(default=None, ge=2, le=360)
    installment_interval: Literal["monthly", "weekly", "biweekly"] | None = None
    installment_amount_basis: Literal["total", "installment"] | None = None
    installment_start_index: int | None = Field(default=None, ge=1, le=360)

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
    card_name: str | None = None
    category_name: str | None = None
    competence_date: date | None = None
    due_date: date | None = None
    payment_date: date | None = None
    transaction_date: date | None = None
    status: Literal["actual", "planned"] = "actual"
    frequency: Literal["daily", "weekly", "monthly"] | None = None
    recurrence_end_date: date | None = None
    installment_count: int | None = Field(default=None, ge=2, le=360)
    installment_interval: Literal["monthly", "weekly", "biweekly"] | None = None
    installment_amount_basis: Literal["total", "installment"] | None = None
    installment_start_index: int | None = Field(default=None, ge=1, le=360)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str) -> str:
        return correct_movement_description(v)[:255]

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        decimal_to_cents(v)
        return v


class UpdateTransferInput(BaseModel):
    transaction_id: int | None = None
    amount: str | None = None
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
            return v
        return correct_movement_description(str(v))[:255]

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
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
    invoice_due_month: int | None = Field(default=None, ge=1, le=12)
    invoice_due_year: int | None = Field(default=None, ge=2000, le=2100)

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
    status: Literal["actual", "planned", "all"] = "all"
    start_date: date | None = None
    end_date: date | None = None


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
    account_type: Literal["corrente", "poupanca", "carteira"]
    institution: str | None = None
    opening_balance: str | None = None
    opening_balance_date: date | None = None

    @field_validator("opening_balance")
    @classmethod
    def validate_opening_balance(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            decimal_to_cents(v)
        return v


class CreateCardInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    institution: str | None = None
    credit_limit: str | None = None
    closing_day: int = Field(ge=1, le=31)
    due_day: int = Field(ge=1, le=31)
    settlement_account_name: str = Field(min_length=1, max_length=100)

    @field_validator("settlement_account_name")
    @classmethod
    def validate_settlement_account_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Conta de liquidação é obrigatória.")
        return v.strip()

    @field_validator("credit_limit")
    @classmethod
    def validate_credit_limit(cls, v: str | None) -> str | None:
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
    account_type: Literal["corrente", "poupanca", "carteira"] | None = None
    opening_balance: str | None = None
    opening_balance_date: date | None = None

    @field_validator("opening_balance")
    @classmethod
    def validate_opening_balance(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            decimal_to_cents(v)
        return v


class UpdateCardInput(BaseModel):
    card_id: int | None = None
    card_name: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    institution: str | None = None
    credit_limit: str | None = None
    closing_day: int | None = Field(default=None, ge=1, le=31)
    due_day: int | None = Field(default=None, ge=1, le=31)
    settlement_account_name: str | None = None

    @field_validator("credit_limit")
    @classmethod
    def validate_credit_limit(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            decimal_to_cents(v)
        return v


class DeleteCardInput(BaseModel):
    card_id: int | None = None
    card_name: str | None = None


class PayInvoiceInput(BaseModel):
    invoice_id: int | None = None
    account_name: str | None = None
    from_account_name: str
    payment_date: date | None = None
    due_month: int | None = None
    due_year: int | None = None


class ToolCall(BaseModel):
    tool: Literal[
        "register_expense",
        "register_income",
        "register_transfer",
        "realize_planned",
        "update_transfer",
        "update_transaction",
        "delete_transaction",
        "update_account",
        "update_card",
        "delete_card",
        "list_transactions",
        "list_accounts",
        "list_categories",
        "get_summary",
        "get_budget_status",
        "categorize",
        "create_account",
        "create_card",
        "create_category",
        "list_invoices",
        "pay_invoice",
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
