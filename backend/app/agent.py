from __future__ import annotations

import json
import os
import re
import asyncio
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from .models import Finding


class AuditAgent:
    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")

    @property
    def hosted_available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    async def answer(self, question: str, findings: list[Finding], case_summary: dict[str, Any]) -> dict[str, Any]:
        deterministic = self._deterministic_answer(question, findings, case_summary)
        if not self.hosted_available:
            return deterministic
        evidence = [
            {
                "finding_id": finding.finding_id,
                "title": finding.title,
                "status": finding.status,
                "summary": finding.summary,
                "financial_effect": finding.financial_effect,
                "why_suspicious": finding.why_suspicious,
                "benign_explanations": finding.benign_explanations,
                "missing_evidence": finding.missing_evidence,
                "anchor_ids": finding.supporting_anchor_ids[:12],
                "calculations": [calculation.model_dump(mode="json") for calculation in finding.calculations],
            }
            for finding in findings
        ]
        prompt = {
            "question": question,
            "findings": evidence,
            "reconciliations": case_summary.get("reconciliations", []),
        }
        try:
            body = {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an audit assistant. Use only the supplied evidence. Return JSON with "
                            "answer, finding_ids, and anchor_ids. Every number must occur verbatim in the "
                            "evidence. Say when evidence is missing. Never infer guilt from a weak signal."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, default=str)},
                ],
            }
            payload = await asyncio.to_thread(self._post_json, body)
            content = payload["choices"][0]["message"]["content"]
            drafted = json.loads(content)
            if not self._supported(drafted, prompt):
                return deterministic
            selected_ids = [
                item
                for item in drafted.get("finding_ids", [])
                if any(finding.finding_id == item for finding in findings)
            ]
            selected = [finding for finding in findings if finding.finding_id in selected_ids]
            if not selected:
                return deterministic
            verified_answer = "\n\n".join(
                f"{finding.title}: {finding.summary} {finding.financial_effect}"
                for finding in selected
            )
            return {
                "answer": verified_answer,
                "finding_ids": selected_ids,
                "anchor_ids": unique_anchors(selected)[:12],
                "mode": "hosted-verified",
            }
        except (urlerror.URLError, KeyError, ValueError, TypeError, json.JSONDecodeError):
            return deterministic

    def _post_json(self, body: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=encoded,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlrequest.urlopen(request, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _supported(drafted: dict[str, Any], evidence: dict[str, Any]) -> bool:
        answer = str(drafted.get("answer", ""))
        evidence_text = json.dumps(evidence, ensure_ascii=False, default=str)
        answer_numbers = set(re.findall(r"(?<![A-Za-z])\d[\d.,]*", answer))
        return all(number in evidence_text for number in answer_numbers)

    @staticmethod
    def _deterministic_answer(question: str, findings: list[Finding], case_summary: dict[str, Any]) -> dict[str, Any]:
        q = question.lower()
        active = [finding for finding in findings if str(finding.status) != "cleared"]
        if any(term in q for term in ("vendor", "lieferant", "same user", "segregation", "shell")):
            selected = [finding for finding in active if "vendor" in finding.tags]
        elif any(term in q for term in ("split", "payment", "zahlung", "threshold", "limit")):
            selected = [finding for finding in active if "payments" in finding.tags]
        elif any(term in q for term in ("asset", "repair", "capex", "anlage", "reparatur")):
            selected = [finding for finding in active if "fixed-assets" in finding.tags]
        elif any(term in q for term in ("cutoff", "cut-off", "december", "january", "period", "accrual")):
            selected = [finding for finding in active if "cutoff" in finding.tags]
        elif any(term in q for term in ("clean", "reconcile", "false positive", "decoy")):
            controls = case_summary.get("precision_controls", [])
            labels = "; ".join(str(control.get("label")) for control in controls if control.get("status") == "cleared")
            return {
                "answer": f"The precision review cleared these unusual but supported items: {labels}.",
                "finding_ids": [],
                "anchor_ids": [],
                "mode": "deterministic",
            }
        else:
            selected = active[:4]

        if not selected:
            return {
                "answer": "No promoted finding matches that question. Try asking about vendor controls, split payments, capitalized repairs, cut-off, or cleared items.",
                "finding_ids": [],
                "anchor_ids": [],
                "mode": "deterministic",
            }
        answer_parts = [f"{finding.title}: {finding.summary}" for finding in selected]
        return {
            "answer": "\n\n".join(answer_parts),
            "finding_ids": [finding.finding_id for finding in selected],
            "anchor_ids": unique_anchors(selected)[:12],
            "mode": "deterministic",
        }


def unique_anchors(findings: list[Finding]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for finding in findings:
        for anchor_id in finding.supporting_anchor_ids:
            if anchor_id not in seen:
                seen.add(anchor_id)
                result.append(anchor_id)
    return result
