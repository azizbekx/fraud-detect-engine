from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

from app.models import DatasetRole
from app.semantics import infer_role, infer_semantic_map, parse_decimal
from app.service import CaseService
from app.store import AuditStore


DOSSIER = Path(__file__).resolve().parents[2] / "Uebungsdaten Muster Verpackungen"


class SampleRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ledgerlens-tests-")
        cls.service = CaseService(AuditStore(cls.temp_dir.name))
        cls.case_id = cls.service.ingest_path(DOSSIER, "Practice regression")
        cls.case = cls.service.store.get_case(cls.case_id)
        cls.findings = cls.service.store.get_findings(cls.case_id)
        cls.active = {finding.rule_id: finding for finding in cls.findings if finding.status != "cleared"}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_ingestion_is_complete_and_immutable(self) -> None:
        integrity = self.case.summary["integrity"]
        self.assertEqual(self.case.source_count, 35)
        self.assertEqual(self.case.coverage_percent, 100)
        self.assertEqual(integrity["parsed_count"], 35)
        self.assertEqual(integrity["error_count"], 0)
        self.assertEqual(integrity["manifest_hashes_verified"], 8)
        self.assertTrue(integrity["immutable"])

    def test_core_reconciliations_tie(self) -> None:
        reconciliations = {item["id"]: item for item in self.case.summary["reconciliations"]}
        self.assertEqual(reconciliations["gl-balance"]["value"], 6351)
        self.assertEqual(reconciliations["gl-balance"]["status"], "passed")
        self.assertEqual(reconciliations["debit-credit"]["status"], "passed")
        self.assertEqual(reconciliations["sales-dispatch"]["detail"], "2,040/2,040 invoices matched; 1 credit-note exception")
        self.assertEqual(reconciliations["subledger-tie"]["status"], "passed")
        self.assertEqual(reconciliations["statement-trace"]["status"], "passed")
        self.assertEqual(reconciliations["statement-trace"]["value"], "2599841.80")
        self.assertTrue(reconciliations["statement-trace"]["anchor_ids"])
        self.assertEqual(reconciliations["claim-lineage"]["status"], "passed")

    def test_precision_first_findings_match_expected_layers(self) -> None:
        self.assertEqual(set(self.active), {
            "vendor-lifecycle-control-override",
            "capex-vs-repair",
            "subsequent-invoice-cutoff",
            "payment-threshold-structuring",
            "journal-approval-chronology",
        })
        self.assertEqual(self.active["vendor-lifecycle-control-override"].monetary_impact, Decimal("248000.00"))
        self.assertEqual(self.active["capex-vs-repair"].monetary_impact, Decimal("150800.00"))
        self.assertEqual(self.active["subsequent-invoice-cutoff"].monetary_impact, Decimal("192000.00"))
        split = self.active["payment-threshold-structuring"]
        self.assertEqual(split.status, "control_breach")
        self.assertEqual(split.calculations[0].result, "39040.00")
        self.assertIsNone(split.monetary_impact)
        self.assertEqual(self.active["journal-approval-chronology"].status, "control_breach")

    def test_updated_cutoff_treatment_does_not_offset_unrelated_accrual(self) -> None:
        cutoff = self.active["subsequent-invoice-cutoff"]
        self.assertEqual(cutoff.calculations[0].result, "192000.00")
        self.assertEqual(len(cutoff.calculations[0].inputs), 8)
        self.assertGreater(len(cutoff.contradicting_anchor_ids), 0)

    def test_headline_and_calculation_lineage(self) -> None:
        headline = self.case.summary["headline"]
        self.assertEqual(headline["profit_overstatement"], "342800.00")
        self.assertEqual(headline["cash_at_risk"], "295120.00")
        self.assertEqual(headline["cleared_controls"], 7)
        self.assertEqual(self.case.summary["unsupported_claims"], 0)
        for finding in self.active.values():
            self.assertTrue(finding.supporting_anchor_ids)
            for calculation in finding.calculations:
                self.assertTrue(calculation.inputs)
                self.assertTrue(all(item.anchor_ids for item in calculation.inputs))
                if calculation.unit == "EUR":
                    total = sum((Decimal(str(item.value)) for item in calculation.inputs), Decimal("0"))
                    self.assertEqual(total, Decimal(str(calculation.result)))

    def test_declared_schema_is_preserved_but_mislabeled_fields_are_visible(self) -> None:
        overrides = {item["semantic_field"]: item for item in self.case.summary["semantic_overrides"]}
        self.assertEqual(overrides["capture_id"]["declared_field"], "ERFASSUNGSNUMMER")
        self.assertEqual(overrides["capture_id"]["inferred_field"], "GEGENKONTO")
        self.assertEqual(overrides["journal_name"]["inferred_field"], "DOKUMENT")

    def test_decoys_are_not_promoted(self) -> None:
        active_text = " ".join(f"{finding.title} {finding.summary}" for finding in self.active.values()).lower()
        for clean_lead in ("nordlicht", "vega werkstoffe", "asset disposal", "invoice correction"):
            self.assertNotIn(clean_lead, active_text)
        cleared_ids = {item["id"] for item in self.case.summary["precision_controls"]}
        self.assertEqual(cleared_ids, {
            "capital-project", "similar-vendors", "clean-new-vendor", "customer-rebates",
            "related-party", "asset-disposal", "invoice-reversal",
        })

    def test_export_is_self_contained(self) -> None:
        archive = zipfile.ZipFile(io.BytesIO(self.service.export_case(self.case_id)))
        self.assertEqual(set(archive.namelist()), {"audit-report.html", "audit-report.pdf", "evidence.json"})
        self.assertTrue(archive.read("audit-report.pdf").startswith(b"%PDF"))
        self.assertIn(b"unsupported_claims", archive.read("evidence.json"))

    def test_model_disabled_chat_remains_useful_and_cited(self) -> None:
        answer = asyncio.run(self.service.ask(self.case_id, "show split payments below the approval limit"))
        self.assertEqual(answer["mode"], "deterministic")
        self.assertIn("39,040.00", answer["answer"])
        self.assertTrue(answer["finding_ids"])
        self.assertTrue(answer["anchor_ids"])


class MutationSafetyTests(unittest.TestCase):
    def test_locale_numbers_and_changed_thresholds(self) -> None:
        self.assertEqual(parse_decimal("10.000"), Decimal("10000"))
        self.assertEqual(parse_decimal("9.780,50"), Decimal("9780.50"))
        self.assertEqual(parse_decimal("9,780.50"), Decimal("9780.50"))
        self.assertEqual(parse_decimal("9780.50"), Decimal("9780.50"))

    def test_renamed_english_columns_map_by_semantics(self) -> None:
        headers = ["Vendor Number", "Transaction ID", "Posting Date", "Amount", "Currency Code", "Narrative"]
        mapping = infer_semantic_map(headers)
        self.assertEqual(mapping["vendor_id"], "Vendor Number")
        self.assertEqual(mapping["booking_id"], "Transaction ID")
        self.assertEqual(mapping["amount"], "Amount")
        self.assertEqual(infer_role(headers, "random-export-42", mapping), DatasetRole.VENDOR_LEDGER)

    def test_runtime_rules_contain_no_sample_entity_or_transaction_literals(self) -> None:
        backend = Path(__file__).resolve().parents[1] / "app"
        runtime = "\n".join(path.read_text(encoding="utf-8") for path in backend.glob("*.py"))
        for literal in ("209101", "200007", "Ratio Consulting", "MV-U05", "9780", "150800", "192000"):
            self.assertNotIn(literal, runtime)


if __name__ == "__main__":
    unittest.main()
