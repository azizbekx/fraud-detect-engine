from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Annotated, AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .models import AskRequest, ReviewDecision
from .service import CaseService


service = CaseService()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if os.getenv("AUTO_LOAD_SAMPLE", "0").lower() in {"1", "true", "yes"}:
        service.ensure_sample()
    yield


app = FastAPI(
    title="LedgerLens Precision Audit API",
    version="0.1.0",
    description="Evidence-native reconciliation and fraud investigation for auditors.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(KeyError)
async def not_found(_: Request, error: KeyError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"Not found: {error.args[0]}"})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ledgerlens", "version": app.version}


@app.get("/api/cases")
def list_cases():
    return service.store.list_cases()


@app.post("/api/cases", status_code=201)
def create_case(
    files: Annotated[list[UploadFile], File(description="One ZIP or a set of dossier files")],
    name: Annotated[str, Form()] = "Uploaded dossier",
):
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one file or ZIP archive.")
    uploads = [(upload.filename or "source", upload.file) for upload in files]
    try:
        case_id = service.ingest_uploads(uploads, name=name, analyze=True)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return service.store.get_case(case_id)


@app.post("/api/cases/sample", status_code=201)
def create_sample_case():
    sample = os.getenv("SAMPLE_DOSSIER")
    if not sample:
        raise HTTPException(status_code=404, detail="SAMPLE_DOSSIER is not configured.")
    try:
        case_id = service.ingest_path(sample, "Muster Verpackungen — Practice Dossier", analyze=True)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return service.store.get_case(case_id)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    return service.store.get_case(case_id)


@app.post("/api/cases/{case_id}/analyze")
def analyze_case(case_id: str):
    service.store.get_case(case_id)
    return service.analyze(case_id)


@app.get("/api/cases/{case_id}/sources")
def get_sources(case_id: str):
    service.store.get_case(case_id)
    return service.store.get_sources(case_id)


@app.get("/api/cases/{case_id}/findings")
def get_findings(case_id: str, include_cleared: bool = True):
    service.store.get_case(case_id)
    return service.store.get_findings(case_id, include_cleared=include_cleared)


@app.get("/api/findings/{finding_id}/trace")
def get_trace(finding_id: str):
    finding = service.store.get_finding(finding_id)
    anchor_ids = list(dict.fromkeys(finding.supporting_anchor_ids + finding.contradicting_anchor_ids))
    anchors = [service.store.get_anchor(anchor_id) for anchor_id in anchor_ids]
    source_ids = list(dict.fromkeys(anchor.source_id for anchor in anchors))
    sources = [service.store.get_source(source_id) for source_id in source_ids]
    return {
        "finding": finding,
        "calculations": finding.calculations,
        "graph": finding.evidence_graph,
        "anchors": anchors,
        "sources": sources,
    }


@app.get("/api/anchors/{anchor_id}")
def get_anchor(anchor_id: str):
    anchor = service.store.get_anchor(anchor_id)
    source = service.store.get_source(anchor.source_id)
    return {"anchor": anchor, "source": source}


@app.get("/api/sources/{source_id}/file")
def get_source_file(source_id: str):
    source = service.store.get_source(source_id)
    path = service.store.source_file_path(source_id)
    return FileResponse(path, media_type=source.media_type, filename=source.name)


@app.post("/api/cases/{case_id}/ask")
async def ask(case_id: str, prompt: AskRequest, request: Request):
    service.store.get_case(case_id)
    answer = await service.ask(case_id, prompt.question)
    if "text/event-stream" not in request.headers.get("accept", ""):
        return answer

    async def events() -> AsyncIterator[str]:
        words = answer["answer"].split(" ")
        for index in range(0, len(words), 18):
            yield f"data: {json.dumps({'type': 'text', 'text': ' '.join(words[index:index + 18]) + ' '}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'evidence', **answer}, ensure_ascii=False)}\n\n"
        yield "data: {\"type\":\"done\"}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.patch("/api/findings/{finding_id}/review")
def review_finding(finding_id: str, decision: ReviewDecision):
    return service.store.update_review(finding_id, str(decision.state), decision.note)


@app.get("/api/cases/{case_id}/export")
def export_case(case_id: str):
    service.store.get_case(case_id)
    payload = service.export_case(case_id)
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="ledgerlens-{case_id}-audit-pack.zip"'},
    )
