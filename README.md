# Lumen

Turn a research question into a cited paper.

Lumen is an AI research platform that automates the full academic research pipeline: literature search, hypothesis generation, experiment execution, and manuscript compilation. It uses coordinated AI agent swarms (GPT-5) to produce publication-ready LaTeX papers grounded in real sources and validated through code experiments.

## What it does

1. **Describe your question** — Write a research topic in plain English
2. **Literature is searched** — Agents query arXiv, Semantic Scholar, DOAJ, and OpenAlex in parallel. PDFs are downloaded and full-text indexed.
3. **Hypotheses are tested** — AI generates testable claims from the literature, writes Python experiments (Monte Carlo simulations, statistical tests, sensitivity analyses), runs them in a sandbox, and evaluates results
4. **Paper is compiled** — Complete LaTeX manuscript with `\cite{}` references, structured sections, and full bibliography

## Architecture

```
User creates project
    ├── InitialResearchServiceManager
    │   ├── Formalizer Agent (improves abstract)
    │   ├── Literature Reviewer Agent (multi-source search + linking)
    │   ├── Literature Summarizer Agent (synthesizes findings)
    │   └── Hypothesizer Agent (proposes testable hypotheses)
    ├── PaperDraftServiceManager
    │   └── Drafting Agent (abstract + literature review)
    ├── HypothesisTestingServiceManager
    │   ├── Research Agent (background research per hypothesis)
    │   ├── Sim Decider Agent (should we run an experiment?)
    │   ├── Simulation Agent (writes + executes Python code)
    │   └── Answer Agent (evaluates: supported/rejected/inconclusive)
    └── CompilationServiceManager
        └── Compilation Agent (full LaTeX manuscript)
```

**11 specialized AI agents** coordinate across 4 pipeline stages. Each agent has specific tools, output schemas, and reasoning configurations. The pipeline runs automatically on project creation and can be re-triggered per-stage.

## Tech stack

- **Backend**: Django 5.2, Django REST Framework, Django-Q2 (task queue)
- **AI**: OpenAI Agents SDK, GPT-5 with extended reasoning
- **Literature**: arXiv API, Semantic Scholar, DOAJ, OpenAlex
- **Database**: SQLite (dev) / PostgreSQL (production via `DATABASE_URL`)
- **Experiments**: Sandboxed Python subprocess execution with resource limits
- **Frontend**: Server-rendered Django templates, Tailwind CSS, CodeMirror 6, Chart.js

## Quick start

```bash
git clone https://github.com/asalsali/lumen.git
cd lumen

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://localhost:8000, sign up, create a project, and watch the agents work.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key with GPT-5 access |
| `SECRET_KEY` | No | Django secret key (auto-generated in dev) |
| `DEBUG` | No | `True` for development (default) |
| `DATABASE_URL` | No | PostgreSQL connection string (uses SQLite if unset) |
| `OPENALEX_MAILTO` | No | Email for OpenAlex polite pool |
| `SEMANTIC_SCHOLAR_API_KEY` | No | Semantic Scholar API key for higher rate limits |
| `SIM_TIMEOUT` | No | Experiment execution timeout in seconds (default: 120) |

## Docker

```bash
docker-compose up --build
```

Three services: **web** (Django + Gunicorn), **db** (PostgreSQL 16), **worker** (Django-Q2 background tasks).

## API

REST API at `/api/` with endpoints for all resources:

```
GET/POST  /api/projects/
GET/POST  /api/papers/
GET       /api/literature/
GET       /api/hypotheses/
GET       /api/simulations/
GET       /api/chat-messages/
```

Session or Basic Auth.

## Project structure

```
├── agents_sdk/                    # 11 AI agents across 5 systems
│   ├── initial_research_agents/   # Search, summarize, hypothesize
│   ├── hypothesis_testing_agents/ # Research, decide, simulate, evaluate
│   ├── paper_draft_agents/        # Draft abstract + lit review
│   ├── compilation_agents/        # Full LaTeX compilation
│   └── project_chat_agents/       # Interactive assistant (19 tools)
├── main/                          # Django app (15 models, 30+ views)
│   ├── models.py
│   ├── views.py
│   ├── api_views.py               # DRF viewsets
│   ├── serializers.py
│   ├── tasks.py                   # Background pipeline with retries
│   ├── experiment_templates.py
│   ├── utils/
│   │   ├── experiment_utils.py    # Sandboxed code execution
│   │   └── pdf_ingestion.py       # PDF download + text extraction
│   └── tests/                     # 30 tests (pytest + factory_boy)
├── templates/                     # Server-rendered UI
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Tests

```bash
pytest main/tests/ -v
```

## License

MIT
