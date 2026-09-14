<div align="center">

# Lumen

### Turn a research question into a cited paper.

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/Python-3.13+-black.svg)](https://python.org)
[![Django 5.2](https://img.shields.io/badge/Django-5.2-black.svg)](https://djangoproject.com)
[![Tests](https://img.shields.io/badge/Tests-30%20passing-black.svg)](#tests)

<br>

Lumen is an AI research platform that automates the full academic pipeline:<br>
**literature search → hypothesis generation → experiment execution → manuscript compilation.**

11 coordinated AI agents. 4 academic databases. Real Python experiments. Publication-ready LaTeX.

<br>

</div>

---

## How it works

```
                    ┌─────────────────────┐
                    │   Your question     │
                    │  "How do export     │
                    │   controls affect   │
                    │   chip supply       │
                    │   chains?"          │
                    └────────┬────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  arXiv   │  │ Semantic │  │  DOAJ /  │
        │          │  │ Scholar  │  │ OpenAlex │
        └────┬─────┘  └────┬─────┘  └────┬─────┘
             └──────────────┼──────────────┘
                            ▼
                   ┌─────────────────┐
                   │  17 papers found │
                   │  PDFs downloaded │
                   │  Full-text indexed│
                   └────────┬────────┘
                            ▼
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         ┌────────┐   ┌────────┐   ┌────────┐
         │  H1 ✓  │   │  H2 ✓  │   │  H3 ✗  │
         │Supported│   │Partial │   │Rejected│
         └───┬────┘   └───┬────┘   └───┬────┘
             └─────────────┼─────────────┘
                           ▼
                  ┌──────────────────┐
                  │ Python experiments│
                  │ Monte Carlo      │
                  │ n=10,000         │
                  │ p=0.003 → PASS   │
                  └────────┬─────────┘
                           ▼
                  ┌──────────────────┐
                  │                  │
                  │  Complete LaTeX  │
                  │  manuscript      │
                  │                  │
                  │  7,000 words     │
                  │  42 citations    │
                  │  \cite{} refs    │
                  │  Full biblio     │
                  │                  │
                  └──────────────────┘
```

## Quick start

```bash
git clone https://github.com/asalsali/lumen.git
cd lumen
pip install -r requirements.txt

cp .env.example .env
# Add your OPENAI_API_KEY to .env

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open [localhost:8000](http://localhost:8000). Create a project. Watch the agents work.

## The agent pipeline

Lumen runs **11 specialized AI agents** across 4 stages. Each agent has specific tools, structured output schemas, and GPT-5 with extended reasoning.

| Stage | Agents | What happens |
|-------|--------|-------------|
| **1. Literature Review** | Formalizer, Reviewer, Summarizer, Hypothesizer | Refines your question, searches 4 databases in parallel, downloads PDFs, indexes full text, synthesizes findings, proposes testable hypotheses |
| **2. Paper Draft** | Drafting Agent | Generates abstract and literature review section grounded in linked sources |
| **3. Hypothesis Testing** | Research, Sim Decider, Simulation, Answer | For each hypothesis: gathers evidence, decides if experiment needed, writes Python code, runs it in sandbox, evaluates results |
| **4. Compilation** | Compilation Agent | Produces complete LaTeX manuscript with `\cite{}` references, structured sections, and full `\begin{thebibliography}` |

### Agent tools

The agents have access to **19 tools**:

```
literature_search     Search across arXiv, Semantic Scholar, DOAJ, OpenAlex
list_literature       List all papers linked to a project
read_literature       Read a paper's abstract + text (30K chars)
deep_read_literature  Read entire paper without truncation
search_within_literature  Full-text search inside linked papers
link_literature       Link a paper to the project
get_paper             Get current manuscript state
create_experiment     Create a Python experiment
run_experiment        Execute in sandboxed subprocess (120s timeout)
get_experiment        Get experiment results + stdout/stderr
create_hypothesis     Propose a new hypothesis
update_hypothesis_status  Mark as supported/rejected/inconclusive
list_hypotheses       List all hypotheses with evaluation summaries
list_experiments      List all experiments with status
create_note           Save a research note
list_notes / get_note / update_note
pip_install_library   Install Python packages for experiments
```

## Experiment system

Experiments run **real Python code**, not just text generation:

```python
# Agents write code like this:
n_trials = params.get('n_trials', 10000)
results = [monte_carlo_trial() for _ in range(n_trials)]

mean = sum(results) / len(results)
ci_95 = confidence_interval(results, 0.95)
p_value = hypothesis_test(results, null_hypothesis=0.3)

record_result({
    "mean": mean,
    "ci_95": ci_95,
    "p_value": p_value,
    "significant": p_value < 0.05
})
```

- Sandboxed subprocess with sensitive env vars stripped
- Configurable timeout (default 120s)
- Results captured as structured JSON
- Full run history with parameter tracking
- Built-in templates: Monte Carlo, Statistical Tests, Data Analysis
- CodeMirror 6 editor with syntax highlighting

## Project structure

```
lumen/
├── agents_sdk/                     # 11 AI agents
│   ├── initial_research_agents/    # Formalizer, Reviewer, Summarizer, Hypothesizer
│   ├── hypothesis_testing_agents/  # Research, Sim Decider, Simulation, Answer
│   ├── paper_draft_agents/         # Drafting agent
│   ├── compilation_agents/         # LaTeX compilation
│   ├── project_chat_agents/        # Interactive assistant (19 tools)
│   └── activity_log.py             # Real-time step logging
├── main/                           # Django app
│   ├── models.py                   # 15 models
│   ├── views.py                    # 30+ views
│   ├── api_views.py                # REST API (DRF)
│   ├── serializers.py              # API serializers
│   ├── tasks.py                    # Background pipeline + retry logic
│   ├── experiment_templates.py     # Starter templates
│   ├── utils/
│   │   ├── experiment_utils.py     # Sandboxed execution
│   │   └── pdf_ingestion.py        # PDF download + extraction
│   └── tests/                      # 30 tests
├── templates/                      # UI (Tailwind CSS)
├── Dockerfile
├── docker-compose.yml              # Web + PostgreSQL + Worker
└── requirements.txt
```

## API

REST API at `/api/`:

```bash
# List projects
curl -u user:pass http://localhost:8000/api/projects/

# Create project
curl -X POST -u user:pass -H "Content-Type: application/json" \
  -d '{"name": "My Research", "abstract": "..."}' \
  http://localhost:8000/api/projects/

# Get hypotheses
curl -u user:pass http://localhost:8000/api/hypotheses/

# Get experiment results
curl -u user:pass http://localhost:8000/api/simulations/
```

## Docker deployment

```bash
docker-compose up --build
```

| Service | Description |
|---------|-------------|
| `web` | Django + Gunicorn on port 8000 |
| `db` | PostgreSQL 16 |
| `worker` | Django-Q2 background task queue |

## Environment variables

| Variable | Required | Default |
|----------|----------|---------|
| `OPENAI_API_KEY` | **Yes** | — |
| `SECRET_KEY` | No | Auto-generated |
| `DEBUG` | No | `True` |
| `DATABASE_URL` | No | SQLite |
| `OPENALEX_MAILTO` | No | — |
| `SEMANTIC_SCHOLAR_API_KEY` | No | — |
| `SIM_TIMEOUT` | No | `120` |

## Tests

```bash
pytest main/tests/ -v
# 30 passed (models, views, API, agent managers)
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.2, DRF, Django-Q2 |
| AI | OpenAI Agents SDK, GPT-5 |
| Literature | arXiv, Semantic Scholar, DOAJ, OpenAlex |
| Database | SQLite / PostgreSQL |
| Frontend | Tailwind CSS, CodeMirror 6, Chart.js |
| Deployment | Docker, Gunicorn, nginx-ready |

## License

MIT

---

<div align="center">
<sub>Built by <a href="https://github.com/asalsali">Alex Salsali</a> at the University of Waterloo</sub>
</div>
