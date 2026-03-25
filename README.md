# PlanProof

**Assessability-Aware Multimodal Planning Compliance Validation**

MSc Dissertation — Data Science with Work Placement, 2025–2026
Partner Organisation: Bristol City Council

---

## What Is This?

PlanProof is an AI system that validates UK planning applications against regulatory rules. Unlike existing tools that force binary PASS/FAIL verdicts, PlanProof asks a harder question: **is there enough trustworthy evidence to even evaluate this rule?**

When evidence is insufficient or contradictory, the system returns **NOT_ASSESSABLE** with a minimum evidence request — telling the applicant exactly what's missing. This mirrors how planning officers actually work.

### Core Architecture

```
Planning Application          Pipeline                          Output
  ├─ Forms (PDF)         ───► Classify → Extract → Graph ───►  PASS / FAIL verdicts
  ├─ Drawings (images)   ───► Reconcile → Gate → Assess    ──► NOT_ASSESSABLE verdicts
  └─ Reports (PDF)             → Evaluate rules             ──► Min Evidence Requests
```

**Neurosymbolic approach**: neural methods (LLMs, VLMs) extract facts from documents; symbolic methods (knowledge graph, deterministic rules) evaluate compliance; a confidence-gating layer mediates between them.

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [VS Code](https://code.visualstudio.com/) with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension (recommended)
- An OpenAI API key (for GPT-4o extraction)

### Option A: VS Code Dev Container (recommended)

```bash
# 1. Clone the repo
git clone <repo-url> planproof && cd planproof

# 2. Copy environment config
cp .env.example .env
# Edit .env — defaults to Ollama (free, no API key needed)
# Or set PLANPROOF_LLM_PROVIDER=groq and add a Groq API key

# 3. Open in VS Code
code .
# VS Code will prompt "Reopen in Container" — click yes
# First build takes ~2-3 minutes, then cached

# 4. Inside the container terminal:
make lint        # Check code quality
make typecheck   # Run mypy strict
make test        # Run pytest
```

### Step 2: Start Backing Services (Docker)

```bash
make services-up       # Start Neo4j + Ollama
make ollama-pull       # Download the llama3.1 model
```

> **Note**: Only Neo4j and Ollama run in Docker. Python runs locally on the host.

---

## Configuration

All configuration is documented in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

Quick reference:

| What | File | Purpose |
|------|------|---------|
| Secrets & API keys | `.env` | OpenAI key, Neo4j credentials (never committed) |
| Pipeline defaults | `configs/default.yaml` | Confidence thresholds, ablation toggles, paths |
| Compliance rules | `configs/rules/*.yaml` | One YAML per rule — add rules without code changes |
| Ablation configs | `configs/ablation/*.yaml` | One YAML per experimental configuration |
| Prompt templates | `configs/prompts/*.yaml` | LLM/VLM prompt templates (versioned) |

---

## Project Structure

```
planproof/
├── src/planproof/           # Source code
│   ├── interfaces/          # Protocol definitions (contracts between layers)
│   ├── schemas/             # Pydantic data models
│   ├── ingestion/           # Document classification + extraction (Layer 1)
│   ├── representation/      # Knowledge graph + normalisation (Layer 2)
│   ├── reasoning/           # Reconciliation, gating, assessability, rules (Layer 3)
│   ├── output/              # Reports, evidence requests, API (Layer 4)
│   ├── evaluation/          # Ablation study infrastructure (Layer 5)
│   ├── infrastructure/      # LLM cache, API clients, logging
│   ├── pipeline/            # Step registry orchestrator
│   └── bootstrap.py         # Composition root (dependency wiring)
├── configs/                 # YAML configuration files
├── data/                    # Datasets, cache, results (mostly gitignored)
├── tests/                   # Unit + integration tests
├── docs/                    # Architecture, ADRs, implementation plan
└── docker/                  # Docker Compose for backing services (Neo4j + Ollama)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full component diagram and design rationale.

---

## Documentation

| Document | What it covers |
|----------|---------------|
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Phased build plan, module specs, risk analysis |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component diagram, interface boundaries, data flow |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Every config file explained with examples |
| [EXECUTION_STATUS.md](docs/EXECUTION_STATUS.md) | Current progress tracker (updated per phase) |
| [docs/adr/](docs/adr/) | Architecture Decision Records |

---

## Development

### Make Targets

| Target | What it does |
|--------|-------------|
| `make lint` | Run ruff linter |
| `make typecheck` | Run mypy in strict mode |
| `make test` | Run pytest with coverage |
| `make test-reasoning` | Run reasoning tests with 90% coverage gate |
| `make all` | lint + typecheck + test |
| `make install` | Install project locally in editable mode |
| `make services-up` | Start Neo4j + Ollama (Docker) |
| `make services-down` | Stop backing services |
| `make ollama-pull` | Download llama3.1 model into Ollama |

### Adding a New Compliance Rule

1. Create `configs/rules/r004_your_rule.yaml` with the rule definition
2. If the `evaluation_type` matches an existing one (e.g., `numeric_threshold`), you're done
3. If you need new evaluation logic, create a class in `src/planproof/reasoning/evaluators/` and register it in `bootstrap.py`

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full YAML schema.

---

## Compliance Checks In Scope

| Rule | Description | Type |
|------|-------------|------|
| R001 | Max building height ≤ 8m | Numeric threshold |
| R002 | Min rear garden depth ≥ 10m | Numeric threshold |
| R003 | Max site coverage ≤ 50% | Ratio threshold |
| C1 | Certificate type validity | Enum check |
| C2 | Address consistency (form vs drawing) | Fuzzy string match |
| C3 | Boundary validation (stated vs Land Registry area) | Numeric tolerance |
| C4 | Plan change detection (proposed vs approved) | Attribute diff |

---

## License

This project is part of an MSc dissertation. Contact the author for licensing information.
