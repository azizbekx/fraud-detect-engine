from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from .models import DatasetRole


def normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


ALIASES: dict[str, set[str]] = {
    "account_id": {"sachkontonummer", "konto", "kontonummer", "account", "account_id", "account_number", "gl_account"},
    "account_name": {"sachkontoname", "bezeichnung", "kontobezeichnung", "account_name", "account_description"},
    "account_type": {"sachkontotyp", "kontenart", "account_type"},
    "vendor_id": {"lieferantenkontonummer", "kreditor", "kreditorenkonto", "vendor", "vendor_id", "vendor_number", "supplier_id"},
    "vendor_name": {"lieferantenname", "kreditorname", "vendor_name", "supplier_name"},
    "customer_id": {"kundenkontonummer", "debitor", "debitorenkonto", "customer", "customer_id", "customer_number"},
    "customer_name": {"kundenname", "debitorname", "customer_name"},
    "vat_id": {"lieferantenustidnr", "kundenustidnr", "ust_idnr", "ust_id", "vat_id", "tax_id"},
    "address": {"lieferantenstrasse", "kundenstrasse", "adresse", "strasse", "address", "street"},
    "postal_code": {"lieferantenplz", "kundenplz", "plz", "postal_code", "zip_code"},
    "city": {"lieferantenort", "kundenort", "ort", "city"},
    "country": {"lieferantenstaat", "kundenstaat", "staat", "land", "country"},
    "booking_id": {"buchungsnummer", "buchung", "journalnummer", "booking_id", "entry_id", "transaction_id", "journal_id"},
    "document_id": {"belegnummer", "beleg", "dokument", "document_id", "document_number", "reference"},
    "invoice_id": {"rechnungsnummer", "invoice_id", "invoice_number"},
    "booking_date": {"buchungsdatum", "wertstellung", "booking_date", "posting_date", "value_date"},
    "document_date": {"belegdatum", "fakturadatum", "document_date", "invoice_date"},
    "service_date": {"leistungsdatum", "service_date", "supply_date"},
    "receipt_date": {"wareneingang_datum", "receipt_date", "goods_receipt_date"},
    "issue_date": {"warenausgang_datum", "issue_date", "goods_issue_date", "dispatch_date"},
    "amount": {"buchungsbetrag", "betrag_eur", "buchungswert", "saldo_31_12_2025", "saldo", "amount", "amount_eur", "value", "balance"},
    "opening_balance": {"eb_01_01_2025", "opening_balance", "opening"},
    "debit_amount": {"soll_2025", "soll", "debit", "debit_amount"},
    "credit_amount": {"haben_2025", "haben", "credit", "credit_amount"},
    "currency": {"buchungswaehrung", "waehrung", "currency", "currency_code"},
    "text": {"buchungstext", "bemerkung", "beschreibung", "text", "description", "memo", "narrative"},
    "user_id": {"benutzerkennung", "benutzer", "user_id", "username", "posted_by"},
    "capture_id": {"erfassungsnummer", "capture_id", "workflow_id"},
    "capture_date": {"erfassungsdatum", "erfasst_am", "capture_date", "created_at"},
    "capture_time": {"erfassungszeit", "erfasst_um", "capture_time", "created_time"},
    "journal_name": {"journalname", "journal_name", "journal_code"},
    "creator_id": {"ersteller", "geaendert_von", "creator", "created_by", "changed_by"},
    "approver_id": {"freigeber", "genehmigt_von", "approver", "approved_by"},
    "approval_date": {"freigabedatum", "approval_date", "approved_at"},
    "approval_status": {"freigabestatus", "genehmigt", "approval_status", "approved"},
    "line_count": {"anzahl_zeilen"},
    "absolute_sum": {"summe_abs_eur"},
    "entity_type": {"art"},
    "change_field": {"feld"},
    "old_value": {"wert_alt"},
    "new_value": {"wert_neu"},
    "change_date": {"datum"},
    "asset_id": {"anlagennummer", "asset_id", "asset_number"},
    "asset_name": {"anlagenbezeichnung", "asset_name", "asset_description"},
    "asset_group": {"anlagengruppe", "asset_group", "asset_class"},
    "asset_status": {"status"},
    "booking_type": {"buchungstyp", "buchungsart"},
    "document_type": {"art"},
    "goods_receipt_id": {"wareneingang_nr", "goods_receipt_id", "receipt_id", "grn"},
    "goods_issue_id": {"warenausgang_nr", "goods_issue_id", "dispatch_id"},
    "relationship": {"verhaeltnis"},
    "ownership_percent": {"anteil_prozent"},
    "intercompany_flag": {"ic_kennzeichen"},
    "credit_limit": {"kreditlimit_eur"},
    "utilization": {"ausnutzung_31_12_2025_eur"},
    "can_post": {"buchen"},
    "can_approve": {"journal_freigeben"},
    "can_pay": {"zahlungslauf"},
    "can_create_vendor": {"stammdaten_kreditor_anlegen"},
    "can_manage_periods": {"perioden"},
    "system_admin": {"systemadmin"},
}


ROLE_SIGNATURES: list[tuple[DatasetRole, set[str], set[str]]] = [
    (DatasetRole.GENERAL_LEDGER, {"account_id", "booking_id", "amount"}, {"capture_time", "booking_type"}),
    (DatasetRole.GL_ACCOUNTS, {"account_id", "account_name"}, {"account_type"}),
    (DatasetRole.VENDOR_LEDGER, {"vendor_id", "booking_id", "amount"}, {"booking_type"}),
    (DatasetRole.VENDOR_MASTER, {"vendor_id", "vendor_name"}, {"vat_id", "address"}),
    (DatasetRole.CUSTOMER_LEDGER, {"customer_id", "booking_id", "amount"}, {"booking_type"}),
    (DatasetRole.CUSTOMER_MASTER, {"customer_id", "customer_name"}, {"vat_id", "address"}),
    (DatasetRole.ASSET_LEDGER, {"asset_id", "amount", "booking_type"}, {"asset_group"}),
    (DatasetRole.ASSET_MASTER, {"asset_id", "asset_name"}, {"asset_group", "asset_status"}),
    (DatasetRole.MASTER_CHANGES, {"change_date", "creator_id", "approver_id"}, {"change_field", "new_value"}),
    (DatasetRole.PERMISSIONS, {"user_id", "can_post"}, {"can_pay", "can_create_vendor"}),
    (DatasetRole.GOODS_RECEIPTS, {"goods_receipt_id", "receipt_date", "amount"}, {"vendor_id", "invoice_id"}),
    (DatasetRole.GOODS_ISSUES, {"goods_issue_id", "issue_date", "amount"}, {"customer_id", "invoice_id"}),
    (DatasetRole.JOURNAL_APPROVALS, {"capture_id", "journal_name", "approver_id"}, {"line_count"}),
    (DatasetRole.RELATED_PARTIES, {"relationship", "ownership_percent"}, {"intercompany_flag"}),
    (DatasetRole.CREDIT_LIMITS, {"customer_id", "credit_limit", "utilization"}, set()),
    (DatasetRole.SUBSEQUENT_RECEIPTS, {"booking_date", "customer_id", "amount"}, set()),
]


def infer_semantic_map(headers: Iterable[Any]) -> dict[str, str]:
    normalized = {str(header): normalize_label(header) for header in headers if str(header or "").strip()}
    mapping: dict[str, str] = {}
    for canonical, aliases in ALIASES.items():
        for original, label in normalized.items():
            if label in aliases:
                mapping.setdefault(canonical, original)
    return mapping


def infer_role(
    headers: Iterable[Any],
    title: str = "",
    semantic_map: dict[str, str] | None = None,
) -> DatasetRole:
    mapping = semantic_map or infer_semantic_map(headers)
    concepts = set(mapping)
    normalized_headers = {normalize_label(h) for h in headers}
    title_n = normalize_label(title)

    if "rechnungsnummer" in normalized_headers and "kreditor" in normalized_headers and "leistungsdatum" in normalized_headers:
        return DatasetRole.NEXT_PERIOD_VENDOR_INVOICES
    if "warenausgang_nr" in normalized_headers or "warenausgang" in title_n:
        return DatasetRole.GOODS_ISSUES
    if "rechnungsnummer" in normalized_headers and "debitor" in normalized_headers:
        return DatasetRole.SALES_INVOICES
    if {"konto", "soll_2025", "haben_2025"}.issubset(normalized_headers):
        return DatasetRole.TRIAL_BALANCE
    if "offene_posten" in title_n or "saldenliste_personenkonten" in title_n:
        if "kreditor" in title_n:
            return DatasetRole.VENDOR_OPEN_ITEMS
        if "debitor" in title_n:
            return DatasetRole.CUSTOMER_OPEN_ITEMS

    best_role = DatasetRole.UNKNOWN
    best_score = -1
    for role, required, optional in ROLE_SIGNATURES:
        if not required.issubset(concepts):
            continue
        score = len(required) * 10 + len(optional.intersection(concepts))
        if score > best_score:
            best_role, best_score = role, score
    return best_role


def infer_text_role(text: str) -> DatasetRole:
    normalized = normalize_label(text[:12_000])
    if "journal_entry_testing" in normalized or "zahlungsfreigaben" in normalized or "wesentlichkeit" in normalized:
        return DatasetRole.AUDIT_POLICY
    if "exportprotokoll" in normalized and "sha_256" in normalized:
        return DatasetRole.EXPORT_MANIFEST
    if "jahresabschluss" in normalized and "summe_aktiva" in normalized:
        return DatasetRole.FINANCIAL_STATEMENT
    return DatasetRole.UNKNOWN


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace("\u00a0", "").replace("€", "").replace("EUR", "").strip()
    if not text or text in {"-", "–"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})+", text):
        # Unambiguous German thousands grouping (for example 10.000 EUR).
        # Decimal exports in the dossier use two fractional digits, so they
        # remain untouched.
        text = text.replace(".", "")
    else:
        text = text.replace(" ", "")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return -number if negative else number


DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def truthy(value: Any) -> bool:
    return normalize_label(value) in {"x", "yes", "ja", "true", "1", "freigegeben"}


def canonicalize_row(
    row: dict[str, Any], role: DatasetRole, semantic_map: dict[str, str]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for canonical, original in semantic_map.items():
        value = row.get(original)
        if canonical in {
            "amount",
            "opening_balance",
            "debit_amount",
            "credit_amount",
            "absolute_sum",
            "ownership_percent",
            "credit_limit",
            "utilization",
        }:
            parsed = parse_decimal(value)
            result[canonical] = str(parsed) if parsed is not None else None
        elif canonical.endswith("_date") or canonical in {"booking_date", "document_date", "service_date", "receipt_date", "issue_date", "change_date"}:
            parsed_date = parse_date(value)
            result[canonical] = parsed_date.isoformat() if parsed_date else None
        elif canonical.startswith("can_") or canonical == "system_admin":
            result[canonical] = truthy(value)
        else:
            result[canonical] = str(value).strip() if value is not None else None

    if role == DatasetRole.MASTER_CHANGES:
        result["entity_type"] = str(row.get(semantic_map.get("entity_type", ""), "")).strip()
        result["change_field"] = str(row.get(semantic_map.get("change_field", ""), "")).strip()
        account = row.get("KONTO") or row.get("Konto") or row.get("konto")
        if account is not None:
            account = str(account).strip()
            if normalize_label(result.get("entity_type")) in {"kreditor", "vendor", "lieferant"}:
                result["vendor_id"] = account
            elif normalize_label(result.get("entity_type")) in {"debitor", "customer", "kunde"}:
                result["customer_id"] = account
        result["entity_name"] = str(row.get("NAME", row.get("Name", ""))).strip()

    if role == DatasetRole.PERMISSIONS:
        result["department"] = str(row.get("Abteilung", row.get("ABTEILUNG", ""))).strip()

    if role in {DatasetRole.GENERAL_LEDGER, DatasetRole.TRIAL_BALANCE}:
        account_id = str(result.get("account_id") or "")
        if "-" in account_id:
            result["counterparty_id"] = account_id.rsplit("-", 1)[-1]

    if role == DatasetRole.GOODS_RECEIPTS and not result.get("invoice_id"):
        result["invoice_id"] = str(row.get("RECHNUNGSNUMMER", "")).strip()

    if role in {DatasetRole.SALES_INVOICES, DatasetRole.NEXT_PERIOD_VENDOR_INVOICES}:
        result["document_type"] = str(row.get("ART", row.get("Art", ""))).strip()

    return {key: value for key, value in result.items() if value not in (None, "")}
