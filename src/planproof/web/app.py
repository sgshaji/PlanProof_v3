"""PlanProof Research Demo — FastAPI web application with 8-page narrative."""
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
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


def _describe_test_set(set_id: str, category: str) -> dict:
    """Return human-readable label and description for a test set."""
    if category == "compliant":
        return {
            "label": "Compliant House Extension",
            "description": "3-storey, 4 m height, 22 m garden — all rules pass",
        }
    elif category in ("non_compliant", "noncompliant"):
        return {
            "label": "Building Violation",
            "description": "Height or garden depth exceeds permitted limit",
        }
    else:
        return {
            "label": "Edge Case — Borderline",
            "description": "Measurements close to rule thresholds",
        }


# Figure metadata: filename → (title, interpretation)
_FIGURE_META: dict[str, tuple[str, str]] = {
    "sable_belief_violin.png": (
        "SABLE Belief Distribution",
        "Shows how evidence sufficiency varies across configurations. The full system produces a bimodal distribution: high belief for rules with strong evidence and near-zero for rules lacking evidence. This clean separation enables reliable three-state verdicts.",
    ),
    "sable_false_fail_prevention.png": (
        "False Violation Prevention",
        "The full system with SABLE produces zero false violations across all evaluations. Removing SABLE (ablation_d) produces 93 false violations — applicants would receive incorrect rejection notices for rules they actually comply with. This is the central result: assessability gating prevents the most damaging failure mode.",
    ),
    "robustness_curves.png": (
        "Robustness Under Extraction Noise",
        "Even when extraction noise is artificially increased to 30%, the full system maintains near-zero false violations. SABLE naturally handles noisy input by lowering belief scores, causing uncertain rules to be classified as Not Assessable rather than incorrectly assessed.",
    ),
    "threshold_sensitivity.png": (
        "Threshold Sensitivity Analysis",
        "Precision stays at 1.0 across all threshold values. The threshold controls how cautious the system is (automation rate), not how accurate. Lowering the threshold assesses more rules without introducing errors.",
    ),
    "extraction_accuracy.png": (
        "Extraction Accuracy",
        "The LLM extracts 88.6% of planning-relevant attributes from application forms, with 85.7% of extracted values matching ground truth exactly. Remaining errors are typically unit mismatches or partial extractions.",
    ),
    "extraction_v1_v2_delta.png": (
        "Prompt Improvement: v1 vs v2",
        "The first extraction prompt was too broad (precision 0.30). The narrowed v2 prompt focuses on exactly the attributes needed for validation rules, improving precision to 0.72 while maintaining the same recall. Prompt engineering matters as much as model capability.",
    ),
    "false_fail_matrix.png": (
        "Oracle vs Real Extraction Matrix",
        "A 2x2 experiment: perfect vs noisy extraction, crossed with SABLE on vs off. SABLE produces zero false violations in all four cells. The protection is structural, not dependent on extraction quality.",
    ),
    "sable_three_state_bar.png": (
        "Verdict Distribution Across Configurations",
        "The full system produces 118 PASS + 14 true FAIL + 0 false FAIL. Ablation_d forces every rule into PASS or FAIL, eliminating the safety net. Ablation_a marks everything as Not Assessable since no evidence exists.",
    ),
    "sable_blocking_reasons.png": (
        "Evidence Blocking Reasons",
        "When a rule is Not Assessable, missing evidence dominates as the reason. Low confidence and conflicting sources are secondary. This breakdown identifies where extraction improvements would most increase automation rates.",
    ),
    "sable_belief_vs_plausibility.png": (
        "Belief vs Plausibility",
        "Each point is a rule-evaluation pair. Points on the diagonal have zero ignorance. Points below show uncertainty — the gap between what we know and what we could know. Wide gaps guide officers to where their attention is most needed.",
    ),
    "sable_component_contribution.png": (
        "Component Contribution Analysis",
        "Only SABLE removal causes false violations. Removing SNKG or reconciliation has no effect on false violations for the current rule set. Removing extraction makes the system unable to assess anything — safe but useless.",
    ),
    "sable_concordance_heatmap.png": (
        "Per-Rule Belief Across Configurations",
        "Rules with strong multi-source evidence (like height) maintain high belief across most configurations. Rules depending on single-source evidence drop more readily when components are removed, revealing which rules are most evidence-hungry.",
    ),
    "sable_oracle_vs_real.png": (
        "Oracle vs Real Extraction Beliefs",
        "SABLE beliefs are robust to extraction quality. Whether using perfect oracle extraction or real noisy extraction, belief scores remain comparable, confirming the framework's resilience.",
    ),
    "robustness_true_fails.png": (
        "True Violation Detection Under Noise",
        "True violation detection degrades gracefully as noise increases. At 30% noise, the system catches fewer real violations because noisy evidence causes SABLE to withhold assessment. This is by design — better to miss a violation than to fabricate one.",
    ),
}


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


def _load_statistics() -> dict | None:
    """Load the ablation statistics.json if available."""
    stats_path = Path("data/results/statistics.json")
    return _load_json(stats_path) if stats_path.exists() else None


def _get_test_sets(limit: int = 9) -> list[dict]:
    """Load synthetic test sets for the demo page."""
    test_sets: list[dict] = []
    synthetic_dir = Path("data/synthetic_diverse")
    for category in ["compliant", "non_compliant", "edge_case"]:
        cat_dir = synthetic_dir / category
        if cat_dir.exists():
            for d in sorted(cat_dir.iterdir()):
                if d.is_dir() and (d / "ground_truth.json").exists():
                    meta = _describe_test_set(d.name, category)
                    test_sets.append({
                        "id": d.name,
                        "path": str(d),
                        "category": category,
                        "label": meta["label"],
                        "description": meta["description"],
                    })
    return test_sets[:limit]


def _get_figures() -> list[dict]:
    """Load figure metadata for gallery display."""
    figures: list[dict] = []
    if Path("figures").exists():
        for name in sorted(f.name for f in Path("figures").glob("*.png")):
            title, interpretation = _FIGURE_META.get(name, (
                name.replace(".png", "").replace("_", " ").title(),
                "",
            ))
            figures.append({
                "filename": name,
                "title": title,
                "interpretation": interpretation,
            })
    return figures


# ── Page Routes ──


@app.get("/", response_class=HTMLResponse)
async def index():
    """Redirect root to the first page."""
    return RedirectResponse(url="/problem", status_code=302)


@app.get("/problem", response_class=HTMLResponse)
async def problem_page(request: Request):
    """Page 1: The Problem."""
    return templates.TemplateResponse(
        request=request,
        name="page1_problem.html",
        context={"page": "problem"},
    )


@app.get("/data", response_class=HTMLResponse)
async def data_page(request: Request):
    """Page 2: The Data."""
    # Count real data
    anon_dir = Path("data/anonymised")
    real_sets = []
    real_file_count = 0
    if anon_dir.exists():
        for d in sorted(anon_dir.iterdir()):
            if d.is_dir():
                real_sets.append({"name": d.name})
                real_file_count += sum(1 for f in d.rglob("*") if f.is_file())

    # Count synthetic data
    synthetic_dir = Path("data/synthetic_diverse")
    synthetic_compliant = 0
    synthetic_noncompliant = 0
    synthetic_edge = 0
    for category, counter_name in [("compliant", "synthetic_compliant"),
                                     ("non_compliant", "synthetic_noncompliant"),
                                     ("edge_case", "synthetic_edge")]:
        cat_dir = synthetic_dir / category
        if cat_dir.exists():
            count = sum(1 for d in cat_dir.iterdir() if d.is_dir())
            if category == "compliant":
                synthetic_compliant = count
            elif category == "non_compliant":
                synthetic_noncompliant = count
            else:
                synthetic_edge = count

    return templates.TemplateResponse(
        request=request,
        name="page2_data.html",
        context={
            "page": "data",
            "real_sets": real_sets,
            "real_set_count": len(real_sets),
            "real_file_count": real_file_count,
            "synthetic_total": synthetic_compliant + synthetic_noncompliant + synthetic_edge,
            "synthetic_compliant": synthetic_compliant,
            "synthetic_noncompliant": synthetic_noncompliant,
            "synthetic_edge": synthetic_edge,
        },
    )


@app.get("/extraction", response_class=HTMLResponse)
async def extraction_page(request: Request):
    """Page 3: Extraction Pipeline."""
    return templates.TemplateResponse(
        request=request,
        name="page3_extraction.html",
        context={"page": "extraction"},
    )


@app.get("/snkg", response_class=HTMLResponse)
async def snkg_page(request: Request):
    """Page 4: Knowledge Graph."""
    stats_data = _load_statistics()
    stats = stats_data.get("per_config", {}) if stats_data else {}

    return templates.TemplateResponse(
        request=request,
        name="page4_snkg.html",
        context={
            "page": "snkg",
            "stats": stats,
        },
    )


@app.get("/boundary", response_class=HTMLResponse)
async def boundary_page(request: Request):
    """Page 5: Boundary Verification."""
    return templates.TemplateResponse(
        request=request,
        name="page5_boundary.html",
        context={"page": "boundary"},
    )


@app.get("/sable", response_class=HTMLResponse)
async def sable_page(request: Request):
    """Page 6: SABLE Engine."""
    return templates.TemplateResponse(
        request=request,
        name="page6_sable.html",
        context={"page": "sable"},
    )


@app.get("/ablation", response_class=HTMLResponse)
async def ablation_page(request: Request):
    """Page 7: Ablation Study — the deepest page."""
    stats_data = _load_statistics()
    stats = stats_data.get("per_config", {}) if stats_data else {}
    comparisons = stats_data.get("pairwise_comparisons", []) if stats_data else []
    n_test_sets = stats_data.get("n_test_sets", 33) if stats_data else 33
    n_evaluations = stats_data.get("n_evaluations", 264) if stats_data else 264

    return templates.TemplateResponse(
        request=request,
        name="page7_ablation.html",
        context={
            "page": "ablation",
            "stats": stats,
            "comparisons": comparisons,
            "n_test_sets": n_test_sets,
            "n_evaluations": n_evaluations,
        },
    )


@app.get("/demo", response_class=HTMLResponse)
async def demo_page(request: Request):
    """Page 8: Live Demo."""
    test_sets = _get_test_sets()

    return templates.TemplateResponse(
        request=request,
        name="page8_demo.html",
        context={
            "page": "demo",
            "test_sets": test_sets,
        },
    )


# ── API Endpoints ──


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
