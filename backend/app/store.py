from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb

from .models import Anchor, CaseSummary, Finding, Policy, Record, Source


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, default=str)


class AuditStore:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir or os.getenv("DATA_DIR", ".fraud-detect-data")).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cases_dir = self.data_dir / "cases"
        self.cases_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "ledgerlens.duckdb"
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def _init_schema(self) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    source_count INTEGER DEFAULT 0,
                    dataset_count INTEGER DEFAULT 0,
                    record_count INTEGER DEFAULT 0,
                    finding_count INTEGER DEFAULT 0,
                    active_finding_count INTEGER DEFAULT 0,
                    coverage_percent INTEGER DEFAULT 0,
                    summary_json VARCHAR DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS sources (
                    source_id VARCHAR PRIMARY KEY,
                    case_id VARCHAR NOT NULL,
                    name VARCHAR NOT NULL,
                    relative_path VARCHAR NOT NULL,
                    sha256 VARCHAR NOT NULL,
                    media_type VARCHAR NOT NULL,
                    size BIGINT NOT NULL,
                    roles_json VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    record_count INTEGER NOT NULL,
                    metadata_json VARCHAR NOT NULL,
                    provenance_family VARCHAR NOT NULL
                );
                CREATE TABLE IF NOT EXISTS anchors (
                    anchor_id VARCHAR PRIMARY KEY,
                    case_id VARCHAR NOT NULL,
                    source_id VARCHAR NOT NULL,
                    kind VARCHAR NOT NULL,
                    locator_json VARCHAR NOT NULL,
                    quote VARCHAR,
                    raw_value_json VARCHAR,
                    normalized_value_json VARCHAR,
                    row_hash VARCHAR
                );
                CREATE TABLE IF NOT EXISTS records (
                    record_id VARCHAR PRIMARY KEY,
                    case_id VARCHAR NOT NULL,
                    source_id VARCHAR NOT NULL,
                    dataset_key VARCHAR NOT NULL,
                    role VARCHAR NOT NULL,
                    row_number INTEGER NOT NULL,
                    data_json VARCHAR NOT NULL,
                    canonical_json VARCHAR NOT NULL,
                    anchor_id VARCHAR NOT NULL,
                    raw_hash VARCHAR NOT NULL
                );
                CREATE TABLE IF NOT EXISTS policies (
                    policy_id VARCHAR PRIMARY KEY,
                    case_id VARCHAR NOT NULL,
                    kind VARCHAR NOT NULL,
                    payload_json VARCHAR NOT NULL
                );
                CREATE TABLE IF NOT EXISTS findings (
                    finding_id VARCHAR PRIMARY KEY,
                    case_id VARCHAR NOT NULL,
                    rule_id VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    severity VARCHAR NOT NULL,
                    review_state VARCHAR NOT NULL,
                    payload_json VARCHAR NOT NULL
                );
                """
            )

    def case_path(self, case_id: str) -> Path:
        path = self.cases_dir / case_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_case(self, case_id: str, name: str) -> CaseSummary:
        created = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO cases(case_id,name,status,created_at) VALUES (?,?,?,?)",
                [case_id, name, "ingesting", created],
            )
        self.case_path(case_id).joinpath("originals").mkdir(parents=True, exist_ok=True)
        return self.get_case(case_id)

    def get_case(self, case_id: str) -> CaseSummary:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM cases WHERE case_id=?", [case_id]).fetchone()
            if not row:
                raise KeyError(case_id)
            columns = [d[0] for d in con.description]
        data = dict(zip(columns, row, strict=True))
        data["summary"] = json.loads(data.pop("summary_json") or "{}")
        return CaseSummary(**data)

    def list_cases(self) -> list[CaseSummary]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT case_id FROM cases ORDER BY created_at DESC").fetchall()
        return [self.get_case(row[0]) for row in rows]

    def update_case(self, case_id: str, **changes: Any) -> CaseSummary:
        allowed = {
            "status",
            "source_count",
            "dataset_count",
            "record_count",
            "finding_count",
            "active_finding_count",
            "coverage_percent",
        }
        parts: list[str] = []
        values: list[Any] = []
        for key, value in changes.items():
            if key == "summary":
                parts.append("summary_json=?")
                values.append(_json(value))
            elif key in allowed:
                parts.append(f"{key}=?")
                values.append(value)
        if parts:
            values.append(case_id)
            with self._lock, self._connect() as con:
                con.execute(f"UPDATE cases SET {', '.join(parts)} WHERE case_id=?", values)
        return self.get_case(case_id)

    def clear_case_artifacts(self, case_id: str) -> None:
        with self._lock, self._connect() as con:
            for table in ("findings", "policies", "records", "anchors", "sources"):
                con.execute(f"DELETE FROM {table} WHERE case_id=?", [case_id])

    def save_sources(self, sources: Iterable[Source]) -> None:
        rows = [
            [
                s.source_id,
                s.case_id,
                s.name,
                s.relative_path,
                s.sha256,
                s.media_type,
                s.size,
                _json(s.roles),
                s.status,
                s.record_count,
                _json(s.metadata),
                s.provenance_family,
            ]
            for s in sources
        ]
        if not rows:
            return
        with self._lock, self._connect() as con:
            con.executemany("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def save_anchors(self, anchors: Iterable[Anchor]) -> None:
        rows = [
            [
                a.anchor_id,
                a.case_id,
                a.source_id,
                str(a.kind),
                _json(a.locator),
                a.quote,
                _json(a.raw_value),
                _json(a.normalized_value),
                a.row_hash,
            ]
            for a in anchors
        ]
        if not rows:
            return
        with self._lock, self._connect() as con:
            con.executemany("INSERT INTO anchors VALUES (?,?,?,?,?,?,?,?,?)", rows)

    def save_records(self, records: Iterable[Record]) -> None:
        rows = [
            [
                r.record_id,
                r.case_id,
                r.source_id,
                r.dataset_key,
                str(r.role),
                r.row_number,
                _json(r.data),
                _json(r.canonical),
                r.anchor_id,
                r.raw_hash,
            ]
            for r in records
        ]
        if not rows:
            return
        with self._lock, self._connect() as con:
            con.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    def save_policies(self, policies: Iterable[Policy]) -> None:
        rows = [[p.policy_id, p.case_id, p.kind, _json(p)] for p in policies]
        if not rows:
            return
        with self._lock, self._connect() as con:
            con.executemany("INSERT INTO policies VALUES (?,?,?,?)", rows)

    def save_findings(self, findings: Iterable[Finding]) -> None:
        rows = [
            [
                f.finding_id,
                f.case_id,
                f.rule_id,
                str(f.status),
                str(f.severity),
                str(f.review_state),
                _json(f),
            ]
            for f in findings
        ]
        if not rows:
            return
        with self._lock, self._connect() as con:
            con.executemany("INSERT INTO findings VALUES (?,?,?,?,?,?,?)", rows)

    def get_sources(self, case_id: str) -> list[Source]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT * FROM sources WHERE case_id=? ORDER BY relative_path", [case_id]).fetchall()
            columns = [d[0] for d in con.description]
        result: list[Source] = []
        for row in rows:
            data = dict(zip(columns, row, strict=True))
            data["roles"] = json.loads(data.pop("roles_json"))
            data["metadata"] = json.loads(data.pop("metadata_json"))
            result.append(Source(**data))
        return result

    def get_source(self, source_id: str) -> Source:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT case_id FROM sources WHERE source_id=?", [source_id]).fetchone()
        if not row:
            raise KeyError(source_id)
        for source in self.get_sources(row[0]):
            if source.source_id == source_id:
                return source
        raise KeyError(source_id)

    def get_records(self, case_id: str, role: str | None = None) -> list[Record]:
        query = "SELECT * FROM records WHERE case_id=?"
        params: list[Any] = [case_id]
        if role:
            query += " AND role=?"
            params.append(role)
        query += " ORDER BY source_id,dataset_key,row_number"
        with self._lock, self._connect() as con:
            rows = con.execute(query, params).fetchall()
            columns = [d[0] for d in con.description]
        result: list[Record] = []
        for row in rows:
            data = dict(zip(columns, row, strict=True))
            data["data"] = json.loads(data.pop("data_json"))
            data["canonical"] = json.loads(data.pop("canonical_json"))
            result.append(Record(**data))
        return result

    def get_policies(self, case_id: str) -> list[Policy]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT payload_json FROM policies WHERE case_id=?", [case_id]).fetchall()
        return [Policy(**json.loads(row[0])) for row in rows]

    def get_findings(self, case_id: str, include_cleared: bool = True) -> list[Finding]:
        query = "SELECT payload_json FROM findings WHERE case_id=?"
        params: list[Any] = [case_id]
        if not include_cleared:
            query += " AND status <> 'cleared'"
        query += " ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 WHEN 'low' THEN 4 ELSE 5 END, finding_id"
        with self._lock, self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [Finding(**json.loads(row[0])) for row in rows]

    def get_finding(self, finding_id: str) -> Finding:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT payload_json FROM findings WHERE finding_id=?", [finding_id]).fetchone()
        if not row:
            raise KeyError(finding_id)
        return Finding(**json.loads(row[0]))

    def update_review(self, finding_id: str, state: str, note: str) -> Finding:
        finding = self.get_finding(finding_id)
        finding.review_state = state
        finding.review_note = note
        with self._lock, self._connect() as con:
            con.execute(
                "UPDATE findings SET review_state=?,payload_json=? WHERE finding_id=?",
                [state, _json(finding), finding_id],
            )
        return finding

    def get_anchor(self, anchor_id: str) -> Anchor:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM anchors WHERE anchor_id=?", [anchor_id]).fetchone()
            if not row:
                raise KeyError(anchor_id)
            columns = [d[0] for d in con.description]
        data = dict(zip(columns, row, strict=True))
        data["locator"] = json.loads(data.pop("locator_json"))
        data["raw_value"] = json.loads(data.pop("raw_value_json") or "null")
        data["normalized_value"] = json.loads(data.pop("normalized_value_json") or "null")
        return Anchor(**data)

    def source_file_path(self, source_id: str) -> Path:
        source = self.get_source(source_id)
        root = self.case_path(source.case_id).joinpath("originals").resolve()
        candidate = root.joinpath(source.relative_path).resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("Unsafe source path")
        return candidate
