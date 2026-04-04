"""PlanProof Research Demo — FastAPI web application."""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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

# Persistent run storage
RUNS_DIR = Path("data/runs")
RUNS_DIR.mkdir(parents=True, exist_ok=True)

# Store active pipeline runs
_runs: dict[str, dict] = {}


def _generate_job_id() -> str:
    """Generate a job ID in RUN-{8hex} format."""
    return f"RUN-{uuid.uuid4().hex[:8]}"


def _save_metadata(job_id: str, metadata: dict) -> None:
    """Write metadata.json for a run."""
    run_dir = RUNS_DIR / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    dest = run_dir / "metadata.json"
    dest.write_text(json.dumps(metadata, default=str, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict | list | None:
    """Load a JSON file, returning None on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


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

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "test_sets": test_sets[:9],
            "figures": figures,
        },
    )


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    """Upload files and return a run_id."""
    job_id = _generate_job_id()
    upload_dir = Path(tempfile.mkdtemp(prefix=f"planproof_{job_id}_"))

    for f in files:
        dest = upload_dir / f.filename
        content = await f.read()
        dest.write_bytes(content)

    _runs[job_id] = {"input_dir": str(upload_dir), "status": "pending"}
    _save_metadata(job_id, {
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_type": "upload",
        "source_id": ", ".join(f.filename for f in files),
        "input_dir": str(upload_dir),
        "status": "pending",
    })
    return {"run_id": job_id, "file_count": len(files)}


@app.get("/api/run-test-set/{set_id}")
async def run_test_set(set_id: str):
    """Start pipeline on a pre-loaded test set."""
    for category in ["compliant", "non_compliant", "edge_case", "noncompliant"]:
        candidate = Path("data/synthetic_diverse") / category / set_id
        if candidate.exists():
            job_id = _generate_job_id()
            _runs[job_id] = {"input_dir": str(candidate), "status": "pending"}
            _save_metadata(job_id, {
                "job_id": job_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_type": "test_set",
                "source_id": set_id,
                "input_dir": str(candidate),
                "status": "pending",
            })
            return {"run_id": job_id}
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
        start_time = time.monotonic()
        for stage_result in run_pipeline_stages(input_dir, job_id=run_id):
            # Strip internal keys (non-serializable objects)
            data = stage_result.get("data", {})
            clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
            payload = {
                "stage": stage_result.get("stage"),
                "title": stage_result.get("title"),
                "data": clean_data,
            }
            yield f"data: {json.dumps(payload, default=str)}\n\n"

        # Update metadata with completion status
        duration = round(time.monotonic() - start_time, 1)
        meta_path = RUNS_DIR / run_id / "metadata.json"
        if meta_path.exists():
            meta = _load_json(meta_path) or {}
            meta["status"] = "complete"
            meta["duration_seconds"] = duration
            meta_path.write_text(
                json.dumps(meta, default=str, indent=2), encoding="utf-8"
            )

        yield f"data: {json.dumps({'stage': 'complete', 'message': 'Pipeline finished'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/runs")
async def list_runs():
    """List all historical runs, sorted by timestamp descending."""
    runs: list[dict] = []
    if RUNS_DIR.exists():
        for run_dir in RUNS_DIR.iterdir():
            if not run_dir.is_dir():
                continue
            meta_path = run_dir / "metadata.json"
            meta = _load_json(meta_path) if meta_path.exists() else None
            if meta:
                # Attach summary if available
                summary_path = run_dir / "summary.json"
                if summary_path.exists():
                    meta["summary"] = _load_json(summary_path)
                runs.append(meta)

    runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return {"runs": runs[:50]}


@app.get("/api/runs/{job_id}")
async def get_run(job_id: str):
    """Get full results for a specific historical run."""
    run_dir = RUNS_DIR / job_id
    if not run_dir.exists():
        return JSONResponse({"error": "Run not found"}, status_code=404)

    meta = _load_json(run_dir / "metadata.json") or {}
    summary = _load_json(run_dir / "summary.json")
    stages: list[dict] = []

    stages_dir = run_dir / "stages"
    if stages_dir.exists():
        # Ordered by pipeline sequence
        stage_order = [
            "classification", "extraction", "snkg",
            "reconciliation", "sable", "verdicts", "ablation",
        ]
        for name in stage_order:
            stage_file = stages_dir / f"{name}.json"
            if stage_file.exists():
                stage_data = _load_json(stage_file)
                if stage_data:
                    stages.append(stage_data)

    return {"metadata": meta, "summary": summary, "stages": stages}


@app.get("/api/runs/{job_id}/stage/{stage_name}")
async def get_run_stage(job_id: str, stage_name: str):
    """Get a specific stage's data for a historical run."""
    stage_file = RUNS_DIR / job_id / "stages" / f"{stage_name}.json"
    if not stage_file.exists():
        return JSONResponse({"error": "Stage not found"}, status_code=404)
    return _load_json(stage_file)


@app.get("/api/figures")
async def list_figures():
    """Return list of available dissertation figures."""
    figures_dir = Path("figures")
    if not figures_dir.exists():
        return {"figures": []}
    return {"figures": sorted(f.name for f in figures_dir.glob("*.png"))}
