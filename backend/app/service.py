from __future__ import annotations

import html
import io
import json
import os
import re
import shutil
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .agent import AuditAgent
from .detectors import DetectorEngine
from .models import Anchor, DatasetRole, Finding, FindingStatus, Policy, Record, Source
from .parsers import DossierParser, ParseBundle, stable_id
from .semantics import parse_decimal
from .store import AuditStore


class CaseService:
    def __init__(self, store: AuditStore | None = None) -> None:
        self.store = store or AuditStore()
        self.agent = AuditAgent()

    def ingest_path(self, path: str | Path, name: str | None = None, analyze: bool = True) -> str:
        source_path = Path(path).resolve()
        if not source_path.is_dir():
            raise ValueError(f"Dossier path is not a directory: {source_path}")
        case_id = f"case_{uuid4().hex[:12]}"
        self.store.create_case(case_id, name or source_path.name)
        originals = self.store.case_path(case_id) / "originals"
        for item in source_path.rglob("*"):
            if not item.is_file() or item.name == ".DS_Store":
                continue
            relative = item.relative_to(source_path)
            destination = originals / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
        if analyze:
            self.analyze(case_id)
        return case_id

    def ingest_uploads(
        self,
        uploads: list[tuple[str, BinaryIO]],
        name: str = "Uploaded dossier",
        analyze: bool = True,
    ) -> str:
        case_id = f"case_{uuid4().hex[:12]}"
        self.store.create_case(case_id, name)
        originals = self.store.case_path(case_id) / "originals"
        for filename, handle in uploads:
            safe_name = Path(filename).name
            if safe_name.lower().endswith(".zip"):
                with zipfile.ZipFile(handle) as archive:
                    for member in archive.infolist():
                        if member.is_dir() or member.filename.startswith("__MACOSX/"):
                            continue
                        member_path = Path(member.filename)
                        if member_path.is_absolute() or ".." in member_path.parts:
                            raise ValueError("Unsafe path in ZIP archive")
                        target = (originals / member_path).resolve()
                        if originals.resolve() not in target.parents:
                            raise ValueError("Unsafe path in ZIP archive")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, target.open("wb") as destination:
                            shutil.copyfileobj(source, destination)
            else:
                destination = originals / safe_name
                with destination.open("wb") as output:
                    shutil.copyfileobj(handle, output)
        if analyze:
            self.analyze(case_id)
        return case_id

    def analyze(self, case_id: str) -> dict[str, Any]:
        self.store.update_case(case_id, status="analyzing")
        self.store.clear_case_artifacts(case_id)
        originals = self.store.case_path(case_id) / "originals"
        bundles = DossierParser(case_id, originals).parse_all()
        semantic_overrides = self._resolve_cross_dataset_semantics(bundles)
        sources = [bundle.source for bundle in bundles]
        anchors = [anchor for bundle in bundles for anchor in bundle.anchors]
        records = [record for bundle in bundles for dataset in bundle.datasets for record in dataset.records]
        policies = self._extract_policies(case_id, bundles)

        self.store.save_sources(sources)
        self.store.save_anchors(anchors)
        self.store.save_records(records)
        self.store.save_policies(policies)

        findings, detector_summary = DetectorEngine(case_id, records, sources, policies).run()
        self.store.save_findings(findings)

        integrity = self._integrity_summary(bundles, anchors)
        active = [finding for finding in findings if str(finding.status) != "cleared"]
        profit_overstatement = sum(
            (
                finding.monetary_impact or Decimal("0")
                for finding in active
                if "profit-overstatement" in finding.tags
            ),
            Decimal("0"),
        )
        cash_at_risk = sum(
            (
                next(
                    (
                        Decimal(str(calculation.result))
                        for calculation in finding.calculations
                        if calculation.label == "Cash paid"
                    ),
                    finding.monetary_impact or Decimal("0"),
                )
                for finding in active
                if "cash" in finding.tags
            ),
            Decimal("0"),
        )
        summary = {
            **detector_summary,
            "integrity": integrity,
            "semantic_overrides": semantic_overrides,
            "headline": {
                "active_findings": len(active),
                "profit_overstatement": str(profit_overstatement.quantize(Decimal("0.01"))),
                "cash_at_risk": str(cash_at_risk.quantize(Decimal("0.01"))),
                "cleared_controls": len(detector_summary.get("precision_controls", [])),
            },
            "analysis_version": "0.1.0",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "model_mode": "hosted-available" if self.agent.hosted_available else "deterministic-fallback",
        }
        parsed_sources = [source for source in sources if source.status == "parsed"]
        coverage = round(100 * len(parsed_sources) / len(sources)) if sources else 0
        self.store.update_case(
            case_id,
            status="ready",
            source_count=len(sources),
            dataset_count=sum(len(bundle.datasets) for bundle in bundles),
            record_count=len(records),
            finding_count=len(findings),
            active_finding_count=len(active),
            coverage_percent=coverage,
            summary=summary,
        )
        return summary

    def _resolve_cross_dataset_semantics(self, bundles: list[ParseBundle]) -> list[dict[str, Any]]:
        records = [record for bundle in bundles for dataset in bundle.datasets for record in dataset.records]
        approvals = [record for record in records if str(record.role) == str(DatasetRole.JOURNAL_APPROVALS)]
        gl = [record for record in records if str(record.role) == str(DatasetRole.GENERAL_LEDGER)]
        overrides: list[dict[str, Any]] = []
        if not approvals or not gl:
            return overrides

        approval_ids = {str(record.canonical.get("capture_id", "")) for record in approvals if record.canonical.get("capture_id")}
        approval_names = {str(record.canonical.get("journal_name", "")) for record in approvals if record.canonical.get("journal_name")}
        approval_pairs = {
            str(record.canonical.get("capture_id")): str(record.canonical.get("journal_name"))
            for record in approvals
            if record.canonical.get("capture_id") and record.canonical.get("journal_name")
        }

        def best_column(targets: set[str]) -> tuple[str | None, int]:
            scores: dict[str, int] = defaultdict(int)
            for record in gl:
                for column, value in record.data.items():
                    if str(value).strip() in targets:
                        scores[column] += 1
            return max(scores.items(), key=lambda item: item[1]) if scores else (None, 0)

        capture_column, capture_score = best_column(approval_ids)
        journal_column, journal_score = best_column(approval_names)
        joint_scores: dict[tuple[str, str], int] = defaultdict(int)
        column_order: dict[str, int] = {}
        for record in gl:
            if not column_order:
                column_order = {column: index for index, column in enumerate(record.data)}
            for candidate_capture, candidate_id in record.data.items():
                expected_name = approval_pairs.get(str(candidate_id).strip())
                if not expected_name:
                    continue
                for candidate_journal, candidate_name in record.data.items():
                    if str(candidate_name).strip() == expected_name:
                        joint_scores[(candidate_capture, candidate_journal)] += 1
        if joint_scores:
            capture_column, journal_column = max(
                joint_scores,
                key=lambda pair: (
                    joint_scores[pair],
                    -abs(column_order.get(pair[1], 9_999) - column_order.get(pair[0], 0)),
                ),
            )
            capture_score = journal_score = joint_scores[(capture_column, journal_column)]
        declared_capture_populated = sum(bool(record.canonical.get("capture_id")) for record in gl)
        if capture_column and capture_score >= max(3, len(approval_ids) // 2) and declared_capture_populated < capture_score:
            for record in gl:
                value = str(record.data.get(capture_column, "")).strip()
                if value:
                    record.canonical["capture_id"] = value
            overrides.append(
                {
                    "role": "general_ledger",
                    "semantic_field": "capture_id",
                    "declared_field": "ERFASSUNGSNUMMER",
                    "inferred_field": capture_column,
                    "join_overlap": capture_score,
                    "reason": "Declared field is empty; inferred field joins the approval population.",
                }
            )
        if journal_column and journal_score >= max(3, len(approval_names) // 2):
            for record in gl:
                value = str(record.data.get(journal_column, "")).strip()
                if value:
                    record.canonical["journal_name"] = value
            overrides.append(
                {
                    "role": "general_ledger",
                    "semantic_field": "journal_name",
                    "inferred_field": journal_column,
                    "join_overlap": journal_score,
                    "reason": "Value-profile overlap with approval journal names.",
                }
            )
        return overrides

    def _extract_policies(self, case_id: str, bundles: list[ParseBundle]) -> list[Policy]:
        policies: list[Policy] = []
        for bundle in bundles:
            if DatasetRole.AUDIT_POLICY not in bundle.source.roles:
                continue
            for anchor in bundle.anchors:
                threshold_match = re.search(
                    r"(?:zahlungsfreigaben|payment approvals?).{0,100}?ab\s+([0-9][0-9.\s]*(?:,[0-9]+)?)\s*EUR",
                    anchor.quote,
                    re.IGNORECASE,
                )
                if threshold_match:
                    value = parse_decimal(threshold_match.group(1))
                    if value:
                        policies.append(
                            Policy(
                                policy_id=stable_id("pol", case_id, "payment-threshold", anchor.anchor_id),
                                case_id=case_id,
                                kind="payment_approval_threshold",
                                value=value,
                                unit="EUR",
                                description="Payments at or above this amount require a second approval.",
                                anchor_ids=[anchor.anchor_id],
                            )
                        )
                materiality_match = re.search(
                    r"gesamtwesentlichkeit\s+([0-9][0-9.\s]*(?:,[0-9]+)?)\s*EUR",
                    anchor.quote,
                    re.IGNORECASE,
                )
                if materiality_match:
                    value = parse_decimal(materiality_match.group(1))
                    if value:
                        policies.append(
                            Policy(
                                policy_id=stable_id("pol", case_id, "materiality", anchor.anchor_id),
                                case_id=case_id,
                                kind="overall_materiality",
                                value=value,
                                unit="EUR",
                                description="Overall audit materiality.",
                                anchor_ids=[anchor.anchor_id],
                            )
                        )
        deduplicated: dict[str, Policy] = {}
        for policy in policies:
            deduplicated.setdefault(policy.kind, policy)
        return list(deduplicated.values())

    def _integrity_summary(self, bundles: list[ParseBundle], anchors: list[Anchor]) -> dict[str, Any]:
        errors = [
            {"source": bundle.source.relative_path, "warnings": bundle.warnings}
            for bundle in bundles
            if bundle.warnings
        ]
        manifest_sources = [bundle.source for bundle in bundles if DatasetRole.EXPORT_MANIFEST in bundle.source.roles]
        manifest_text = "".join(
            re.sub(r"\s+", "", anchor.quote)
            for anchor in anchors
            if any(source.source_id == anchor.source_id for source in manifest_sources)
        )
        verifiable = [
            bundle.source
            for bundle in bundles
            if bundle.source.sha256 in manifest_text and bundle.source not in manifest_sources
        ]
        return {
            "source_count": len(bundles),
            "parsed_count": len([bundle for bundle in bundles if bundle.source.status == "parsed"]),
            "unsupported_count": len([bundle for bundle in bundles if bundle.source.status == "unsupported"]),
            "error_count": len([bundle for bundle in bundles if bundle.source.status == "error"]),
            "manifest_hashes_verified": len(verifiable),
            "anchors_created": len(anchors),
            "issues": errors,
            "immutable": True,
        }

    async def ask(self, case_id: str, question: str) -> dict[str, Any]:
        case = self.store.get_case(case_id)
        findings = self.store.get_findings(case_id, include_cleared=True)
        return await self.agent.answer(question, findings, case.summary)

    def export_case(self, case_id: str) -> bytes:
        case = self.store.get_case(case_id)
        findings = self.store.get_findings(case_id, include_cleared=True)
        sources = self.store.get_sources(case_id)
        anchor_ids = list(
            dict.fromkeys(
                anchor_id
                for finding in findings
                for anchor_id in finding.supporting_anchor_ids + finding.contradicting_anchor_ids
            )
        )
        anchors = [self.store.get_anchor(anchor_id) for anchor_id in anchor_ids]
        anchors_by_id = {anchor.anchor_id: anchor for anchor in anchors}
        sources_by_id = {source.source_id: source for source in sources}
        evidence = {
            "case": case.model_dump(mode="json"),
            "findings": [finding.model_dump(mode="json") for finding in findings],
            "sources": [source.model_dump(mode="json") for source in sources],
            "anchors": [anchor.model_dump(mode="json") for anchor in anchors],
            "policies": [policy.model_dump(mode="json") for policy in self.store.get_policies(case_id)],
            "verification": {
                "unsupported_claims": case.summary.get("unsupported_claims", 0),
                "calculation_lineage_complete": case.summary.get("unsupported_claims", 0) == 0,
            },
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        report_html = self._report_html(case.name, findings, case.summary, anchors_by_id, sources_by_id)
        report_pdf = self._report_pdf(case.name, findings, anchors_by_id, sources_by_id)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("audit-report.html", report_html)
            archive.writestr("audit-report.pdf", report_pdf)
            archive.writestr("evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
        return output.getvalue()

    @staticmethod
    def _report_html(
        name: str,
        findings: list[Finding],
        summary: dict[str, Any],
        anchors: dict[str, Anchor],
        sources: dict[str, Source],
    ) -> str:
        cards = []
        for finding in findings:
            calculations = "".join(
                f"<li><strong>{html.escape(calc.label)}:</strong> {html.escape(str(calc.result))} "
                f"{html.escape(calc.unit or '')}<br><code>{html.escape(calc.expression)}</code></li>"
                for calc in finding.calculations
            )
            citations = []
            for anchor_id in finding.supporting_anchor_ids + finding.contradicting_anchor_ids:
                anchor = anchors.get(anchor_id)
                if not anchor:
                    continue
                source = sources.get(anchor.source_id)
                citations.append(
                    "<li>"
                    f"<strong>{html.escape(source.relative_path if source else anchor.source_id)}</strong> — "
                    f"{html.escape(json.dumps(anchor.locator, ensure_ascii=False, default=str))}"
                    f"<blockquote>{html.escape(anchor.quote or str(anchor.raw_value or 'Structured value'))}</blockquote>"
                    f"<code>{html.escape(anchor.anchor_id)}</code></li>"
                )
            cards.append(
                f"""
                <article>
                  <div class="badge">{html.escape(str(finding.status).replace('_', ' '))}</div>
                  <h2>{html.escape(finding.title)}</h2>
                  <p>{html.escape(finding.summary)}</p>
                  <h3>Financial effect</h3><p>{html.escape(finding.financial_effect)}</p>
                  <h3>Calculations</h3><ul>{calculations or '<li>No monetary impact asserted.</li>'}</ul>
                  <h3>Evidence anchors</h3><ol class="citations">{''.join(citations)}</ol>
                </article>
                """
            )
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>LedgerLens Audit Report</title>
        <style>body{{font:15px/1.55 Arial;margin:40px;color:#17282e;background:#f6f4ee}}main{{max-width:960px;margin:auto}}article{{background:white;border:1px solid #dce2df;border-radius:16px;padding:24px;margin:18px 0}}.badge{{color:#a23f29;font-weight:bold;text-transform:uppercase;font-size:12px}}h1{{font-size:34px}}h2{{margin-top:6px}}code{{word-break:break-all;color:#4e6866}}.citations{{padding-left:22px}}.citations li{{margin:12px 0}}blockquote{{margin:6px 0;padding:8px 12px;background:#f2f3ef;border-left:3px solid #6b9c8b;font-family:monospace;font-size:12px}}</style></head>
        <body><main><h1>LedgerLens audit report</h1><p>{html.escape(name)}</p><p>Unsupported claims: {summary.get('unsupported_claims', 0)}</p>{''.join(cards)}</main></body></html>"""

    @staticmethod
    def _report_pdf(
        name: str,
        findings: list[Finding],
        anchors: dict[str, Anchor],
        sources: dict[str, Source],
    ) -> bytes:
        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title="LedgerLens Audit Report",
        )
        styles = getSampleStyleSheet()
        story: list[Any] = [Paragraph("LedgerLens Audit Report", styles["Title"]), Paragraph(html.escape(name), styles["Normal"]), Spacer(1, 6 * mm)]
        for finding in findings:
            story.append(Paragraph(html.escape(finding.title), styles["Heading2"]))
            story.append(
                Table(
                    [[str(finding.status).replace("_", " ").upper(), str(finding.severity).upper()]],
                    colWidths=[70 * mm, 35 * mm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E9F0ED")),
                            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#16323A")),
                            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B6C7C1")),
                            ("PADDING", (0, 0), (-1, -1), 6),
                        ]
                    ),
                )
            )
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(html.escape(finding.summary), styles["BodyText"]))
            story.append(Paragraph(f"<b>Financial effect:</b> {html.escape(finding.financial_effect)}", styles["BodyText"]))
            for calculation in finding.calculations:
                story.append(
                    Paragraph(
                        f"<b>{html.escape(calculation.label)}:</b> {html.escape(str(calculation.result))} "
                        f"{html.escape(calculation.unit or '')} — {html.escape(calculation.expression)}",
                        styles["BodyText"],
                    )
                )
            story.append(Paragraph("<b>Source citations</b>", styles["Heading3"]))
            for anchor_id in (finding.supporting_anchor_ids + finding.contradicting_anchor_ids)[:12]:
                anchor = anchors.get(anchor_id)
                if not anchor:
                    continue
                source = sources.get(anchor.source_id)
                label = source.relative_path if source else anchor.source_id
                locator = json.dumps(anchor.locator, ensure_ascii=False, default=str)
                quote = (anchor.quote or str(anchor.raw_value or "Structured value"))[:500]
                story.append(
                    Paragraph(
                        f"<b>{html.escape(label)}</b> — {html.escape(locator)}<br/>"
                        f"{html.escape(quote)}<br/><font size=7>{html.escape(anchor.anchor_id)}</font>",
                        styles["BodyText"],
                    )
                )
            if len(finding.supporting_anchor_ids + finding.contradicting_anchor_ids) > 12:
                story.append(Paragraph("Complete anchor population is included in evidence.json.", styles["Italic"]))
            story.append(Spacer(1, 5 * mm))
        document.build(story)
        return buffer.getvalue()

    def ensure_sample(self) -> str | None:
        if self.store.list_cases():
            return self.store.list_cases()[0].case_id
        sample = os.getenv("SAMPLE_DOSSIER", "")
        if sample and Path(sample).is_dir():
            return self.ingest_path(sample, "Muster Verpackungen - Practice Dossier", analyze=True)
        return None
