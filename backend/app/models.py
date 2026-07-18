from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetRole(StrEnum):
    GENERAL_LEDGER = "general_ledger"
    GL_ACCOUNTS = "gl_accounts"
    VENDOR_MASTER = "vendor_master"
    VENDOR_LEDGER = "vendor_ledger"
    CUSTOMER_MASTER = "customer_master"
    CUSTOMER_LEDGER = "customer_ledger"
    ASSET_MASTER = "asset_master"
    ASSET_LEDGER = "asset_ledger"
    MASTER_CHANGES = "master_changes"
    PERMISSIONS = "permissions"
    GOODS_RECEIPTS = "goods_receipts"
    GOODS_ISSUES = "goods_issues"
    SALES_INVOICES = "sales_invoices"
    NEXT_PERIOD_VENDOR_INVOICES = "next_period_vendor_invoices"
    JOURNAL_APPROVALS = "journal_approvals"
    RELATED_PARTIES = "related_parties"
    TRIAL_BALANCE = "trial_balance"
    VENDOR_OPEN_ITEMS = "vendor_open_items"
    CUSTOMER_OPEN_ITEMS = "customer_open_items"
    SUBSEQUENT_RECEIPTS = "subsequent_receipts"
    CREDIT_LIMITS = "credit_limits"
    FINANCIAL_STATEMENT = "financial_statement"
    AUDIT_POLICY = "audit_policy"
    EXPORT_MANIFEST = "export_manifest"
    GDPDU_SCHEMA = "gdpdu_schema"
    UNKNOWN = "unknown"


class AnchorKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    DELIMITED = "delimited"
    XML = "xml"
    TEXT = "text"


class SemanticField(StrEnum):
    ACCOUNT_ID = "account_id"
    VENDOR_ID = "vendor_id"
    CUSTOMER_ID = "customer_id"
    DOCUMENT_ID = "document_id"
    BOOKING_ID = "booking_id"
    BOOKING_DATE = "booking_date"
    DOCUMENT_DATE = "document_date"
    SERVICE_DATE = "service_date"
    AMOUNT = "amount"
    CURRENCY = "currency"
    USER_ID = "user_id"


class FindingStatus(StrEnum):
    CONFIRMED_CONTRADICTION = "confirmed_contradiction"
    CONTROL_BREACH = "control_breach"
    STRONG_HYPOTHESIS = "strong_hypothesis"
    NEEDS_EVIDENCE = "needs_evidence"
    CLEARED = "cleared"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ReviewState(StrEnum):
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    EVIDENCE_REQUESTED = "evidence_requested"


class Source(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    source_id: str
    case_id: str
    name: str
    relative_path: str
    sha256: str
    media_type: str
    size: int
    roles: list[DatasetRole] = Field(default_factory=list)
    status: str = "parsed"
    record_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance_family: str


class Anchor(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    anchor_id: str
    case_id: str
    source_id: str
    kind: AnchorKind
    locator: dict[str, Any]
    quote: str = ""
    raw_value: Any | None = None
    normalized_value: Any | None = None
    row_hash: str | None = None


class Record(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    record_id: str
    case_id: str
    source_id: str
    dataset_key: str
    role: DatasetRole
    row_number: int
    data: dict[str, Any]
    canonical: dict[str, Any] = Field(default_factory=dict)
    anchor_id: str
    raw_hash: str


class Entity(BaseModel):
    entity_id: str
    case_id: str
    kind: str
    name: str
    identifiers: dict[str, str] = Field(default_factory=dict)
    anchor_ids: list[str] = Field(default_factory=list)


class Transaction(BaseModel):
    transaction_id: str
    case_id: str
    transaction_type: str
    booking_date: datetime | str | None = None
    amount: Decimal
    currency: str
    counterparty_entity_id: str | None = None
    source_record_ids: list[str] = Field(default_factory=list)
    anchor_ids: list[str] = Field(default_factory=list)


class Policy(BaseModel):
    policy_id: str
    case_id: str
    kind: str
    value: Decimal | str
    unit: str | None = None
    description: str
    anchor_ids: list[str]
    confidence: str = "explicit"


class CalculationInput(BaseModel):
    label: str
    value: Decimal | str
    anchor_ids: list[str] = Field(default_factory=list)


class Calculation(BaseModel):
    calculation_id: str
    label: str
    expression: str
    result: Decimal | str
    unit: str | None = None
    inputs: list[CalculationInput] = Field(default_factory=list)


class EvidenceEdge(BaseModel):
    edge_id: str
    source: str
    target: str
    relation: str
    label: str
    anchor_ids: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    finding_id: str
    case_id: str
    rule_id: str
    title: str
    summary: str
    status: FindingStatus
    severity: Severity
    review_state: ReviewState = ReviewState.UNREVIEWED
    review_note: str = ""
    monetary_impact: Decimal | None = None
    currency: str | None = None
    financial_effect: str
    why_suspicious: list[str]
    benign_explanations: list[str]
    missing_evidence: list[str]
    confidence_rationale: str
    supporting_anchor_ids: list[str]
    contradicting_anchor_ids: list[str] = Field(default_factory=list)
    calculations: list[Calculation] = Field(default_factory=list)
    evidence_graph: list[EvidenceEdge] = Field(default_factory=list)
    provenance_families: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewDecision(BaseModel):
    state: ReviewState
    note: str = ""


class CaseSummary(BaseModel):
    case_id: str
    name: str
    status: str
    created_at: datetime
    source_count: int = 0
    dataset_count: int = 0
    record_count: int = 0
    finding_count: int = 0
    active_finding_count: int = 0
    coverage_percent: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2_000)
