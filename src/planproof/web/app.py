"""PlanProof Research Demo — FastAPI web application."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

app = FastAPI(title="PlanProof Research Demo")

# Static files and templates
WEB_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

# Mount figures directory only if it exists
_figures_dir = Path("figures")
if _figures_dir.exists():
    app.mount("/figures", StaticFiles(directory=_figures_dir), name="figures")

templates = Jinja2Templates(directory=WEB_DIR / "templates")

# Store active pipeline runs
_runs: dict[str, dict] = {}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main demo page."""
    test_sets: list[dict] = []
    synthetic_dir = Path("data/synthetic_diverse")
    for category in ["compliant", "non_compliant", "edge_case"]:
        cat_dir = synthetic_dir / category
        if cat_dir.exists():
            for d in sorted(cat_dir.iterdir()):
                if d.is_dir() and (d / "ground_truth.json").exists():
                    test_sets.append({
                        "id": d.name,
                        "path": str(d),
                        "category": category,
                    })

    figures = (
        sorted(f.name for f in Path("figures").glob("*.png"))
        if Path("figures").exists()
        else []
    )

    return templates.TemplateResponse("index.html", {
        "request": request,
        "test_sets": test_sets[:9],
        "figures": figures,
    })


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    """Upload files and return a run_id."""
    run_id = str(uuid.uuid4())[:8]
    upload_dir = Path(tempfile.mkdtemp(prefix=f"planproof_{run_id}_"))

    for f in files:
        dest = upload_dir / f.filename
        content = await f.read()
        dest.write_bytes(content)

    _runs[run_id] = {"input_dir": str(upload_dir), "status": "pending"}
    return {"run_id": run_id, "file_count": len(files)}


@app.get("/api/run-test-set/{set_id}")
async def run_test_set(set_id: str):
    """Start pipeline on a pre-loaded test set."""
    for category in ["compliant", "non_compliant", "edge_case", "noncompliant"]:
        candidate = Path("data/synthetic_diverse") / category / set_id
        if candidate.exists():
            run_id = str(uuid.uuid4())[:8]
            _runs[run_id] = {"input_dir": str(candidate), "status": "pending"}
            return {"run_id": run_id}
    return {"error": f"Test set {set_id} not found"}


@app.get("/api/stream/{run_id}")
async def stream_pipeline(run_id: str):
    """SSE endpoint — streams pipeline stage results."""
    run = _runs.get(run_id)
    if not run:
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'Run not found'})}\n\n"]),
            media_type="text/event-stream",
        )

    from planproof.web.pipeline_runner import run_pipeline_stages

    async def event_stream() -> AsyncGenerator[str, None]:
        input_dir = Path(run["input_dir"])
        for stage_result in run_pipeline_stages(input_dir):
            # Strip internal keys (non-serializable objects)
            data = stage_result.get("data", {})
            clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
            payload = {
                "stage": stage_result.get("stage"),
                "title": stage_result.get("title"),
                "data": clean_data,
            }
            yield f"data: {json.dumps(payload, default=str)}\n\n"
        yield f"data: {json.dumps({'stage': 'complete', 'message': 'Pipeline finished'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/figures")
async def list_figures():
    """Return list of available dissertation figures."""
    figures_dir = Path("figures")
    if not figures_dir.exists():
        return {"figures": []}
    return {"figures": sorted(f.name for f in figures_dir.glob("*.png"))}
