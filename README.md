# LedgerLens

LedgerLens is a local-first fraud audit agent for mixed financial dossiers. It ingests GDPdU exports, CSV, XLSX, PDF, DOCX, and scanned PDFs; reconciles the accounting population; and promotes only evidence-backed, source-cited fraud hypotheses.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Open [http://localhost:5173](http://localhost:5173). The practice dossier is mounted read-only and loaded automatically on first start.

## Local development

Backend:

```bash
cd backend
uv venv
uv pip install -e '.[dev]'
uv run uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Design rules

- Original files are immutable and addressed by SHA-256.
- Calculations use decimal arithmetic; the LLM never performs reconciliation.
- Every finding includes native anchors and calculation lineage.
- Weak signals never create a finding without corroboration.
- Runtime rules do not contain practice vendor IDs, account IDs, dates, or amounts.
- If no model endpoint is configured, all deterministic analysis and audit chat remain available.

## API

FastAPI documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Tests

```bash
cd backend
uv run pytest -q
```

The sample regression suite validates all four seeded schemes and explicitly clears the seven decoys described by the sealed practice ground truth.

The updated practice labels are reflected correctly: the unrelated EUR 86,500 accrual is retained as counter-evidence and does not reduce the EUR 192,000 cut-off exception.

See [docs/JUDGING_PLAYBOOK.md](docs/JUDGING_PLAYBOOK.md) for final-dossier handling, auditor questions, and the demo sequence.
