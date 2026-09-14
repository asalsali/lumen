from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

from agents import function_tool

from main.models import Project, Paper, Literature, Citation, Simulation, Hypothesis, HypothesisStatus as DjangoHypothesisStatus, Note
from main.research_services import HttpClient, search_all
from main.research_services.types import PaperRecord, asdict_record
from asgiref.sync import sync_to_async

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

# ==========================
# Pydantic Models (Tool I/O)
# ==========================

class SearchInput(BaseModel):
    query: str = Field(description="Search query string")
    limit_per_source: int = Field(default=10, description="Max results per provider")


class SearchResultItem(BaseModel):
    source: str
    source_id: str
    title: str
    abstract: str = ""
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None
    open_access_pdf_url: Optional[str] = None
    venue: Optional[str] = None


class SearchSourceResults(BaseModel):
    provider: str = Field(description="Provider name, e.g., arxiv, openalex")
    papers: List[SearchResultItem]


class SearchResults(BaseModel):
    results: List[SearchSourceResults]


class LiteratureMeta(BaseModel):
    id: int
    title: str
    authors: str = ""
    journal_or_publisher: str = ""
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None
    source_type: str


class LiteratureReadRequest(BaseModel):
    literature_id: int
    max_chars: int = Field(default=30000, ge=100, le=200000)
    include_abstract: bool = True


class LiteratureReadResult(BaseModel):
    id: int
    title: str
    content: str
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None


class LinkLiteratureInput(BaseModel):
    project_id: int
    title: str
    authors: Optional[str] = Field(default="", description="Comma-separated author names")
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None
    open_access_pdf_url: Optional[str] = None
    abstract: Optional[str] = None
    venue: Optional[str] = None


class LinkLiteratureResult(BaseModel):
    literature_id: int
    created: bool
    citation_id: Optional[int] = None


class PaperModel(BaseModel):
    id: int
    title: str
    abstract: str = ""
    content_format: str
    content_raw: str = ""


class ExperimentSummary(BaseModel):
    id: int
    name: str
    description: str = ""
    status: str


class KeyValue(BaseModel):
    name: str
    value: str


class ExperimentDetail(BaseModel):
    id: int
    name: str
    description: str = ""
    code: str
    language: str
    parameters: Optional[List[KeyValue]] = None
    status: str


class HypothesisStatus(str, Enum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class HypothesisModel(BaseModel):
    id: int
    title: str
    statement: str
    status: HypothesisStatus
    evaluation_summary: str = ""
    confidence: Optional[float] = None


class CreateHypothesisInput(BaseModel):
    project_id: int
    title: str
    statement: str


class CreateExperimentInput(BaseModel):
    project_id: int
    name: str
    description: str = ""
    code: str = Field(description="Python code to run for the experiment")
    language: str = Field(default="python")
    parameters: Optional[List[KeyValue]] = None


class UpdateHypothesisStatusInput(BaseModel):
    hypothesis_id: int
    status: HypothesisStatus


class NoteModel(BaseModel):
    id: int
    title: str
    body: str


class CreateNoteInput(BaseModel):
    project_id: int
    title: str
    body: str


# ======
# Tools
# ======

@function_tool
async def literature_search(input: SearchInput) -> SearchResults:
    """Search literature across providers (arXiv/OpenAlex/DOAJ/Semantic Scholar).

    Returns structured results grouped by provider.
    """
    logger.info(f"literature_search(input={input})")
    client = HttpClient()
    try:
        grouped = await search_all(
            client,
            query=input.query,
            limit_per_source=input.limit_per_source,
            mailto=None,
            open_access_only=True,
        )
        # logger.info(f"literature_search(grouped={grouped})")
    finally:
        await client.aclose()
    source_results: List[SearchSourceResults] = []
    for provider, records in (grouped or {}).items():
        items: List[SearchResultItem] = []
        for rec in records or []:
            # rec is a PaperRecord dataclass
            data = asdict_record(rec)
            items.append(
                SearchResultItem(
                    source=data.get("source", provider),
                    source_id=data.get("source_id", ""),
                    title=data.get("title", ""),
                    abstract=data.get("abstract", ""),
                    year=data.get("year"),
                    doi=data.get("doi"),
                    arxiv_id=data.get("arxiv_id"),
                    url=data.get("url"),
                    open_access_pdf_url=data.get("open_access_pdf_url"),
                    venue=data.get("venue"),
                )
            )
        source_results.append(SearchSourceResults(provider=str(provider), papers=items))
    logger.info(f"literature_search(source_results={source_results})")
    return SearchResults(results=source_results)


def _list_literature_sync(project_id: int) -> List[LiteratureMeta]:
    logger.info(f"list_literature(project_id={project_id})")
    project = Project.objects.get(pk=project_id)
    try:
        paper = project.paper
    except Paper.DoesNotExist:
        logger.info(f"list_literature(project_id={project_id}) - Paper does not exist")
        return []
    results: List[LiteratureMeta] = []
    for cit in paper.citations.select_related('literature').order_by('order'):
        lit = cit.literature
        results.append(LiteratureMeta(
            id=lit.id,
            title=lit.title,
            authors=lit.authors or "",
            journal_or_publisher=lit.journal_or_publisher or "",
            year=lit.year,
            doi=lit.doi or None,
            arxiv_id=lit.arxiv_id or None,
            url=lit.url or None,
            source_type=lit.source_type,
        ))
    logger.info(f"list_literature(project_id={project_id}) - results={results}")
    return results


@function_tool
async def list_literature(project_id: int) -> List[LiteratureMeta]:
    """List literature linked to the project's paper (via citations)."""
    logger.info(f"list_literature(project_id={project_id})")
    return await sync_to_async(_list_literature_sync)(project_id)


def _read_literature_sync(request: LiteratureReadRequest) -> LiteratureReadResult:
    logger.info(f"read_literature(request={request})")
    lit = Literature.objects.get(pk=request.literature_id)
    blocks: List[str] = []
    if request.include_abstract and lit.abstract:
        blocks.append(lit.abstract.strip())
    if lit.full_text:
        blocks.append(lit.full_text.strip())
    content = ("\n\n".join(blocks)).strip() or ""
    if len(content) > request.max_chars:
        content = content[: request.max_chars]
    try:
        logger.info(f"read_literature(request={request}) - content={content[:100]}")
    except Exception as e:
        logger.error(f"read_literature(request={request}) - error={e}")
    return LiteratureReadResult(
        id=lit.id,
        title=lit.title,
        content=content,
        year=lit.year,
        doi=lit.doi or None,
        arxiv_id=lit.arxiv_id or None,
        url=lit.url or None,
    )


@function_tool
async def read_literature(request: LiteratureReadRequest) -> LiteratureReadResult:
    """Read literature text up to a maximum number of characters (abstract + full text)."""
    logger.info(f"read_literature(request={request})")
    return await sync_to_async(_read_literature_sync)(request)


@function_tool
async def deep_read_literature(literature_id: int) -> dict:
    """Read the complete full text of a literature record. Use this when you need to deeply understand a paper's methods, results, or specific sections. Returns the full text without truncation."""

    @sync_to_async
    def _get():
        from main.models import Literature
        try:
            lit = Literature.objects.get(pk=literature_id)
        except Literature.DoesNotExist:
            return {"error": f"Literature {literature_id} not found"}

        text = lit.full_text or lit.abstract or ''
        return {
            "id": lit.pk,
            "title": lit.title,
            "authors": lit.authors,
            "year": lit.year,
            "doi": lit.doi,
            "full_text_length": len(text),
            "full_text": text,
            "has_full_text": bool(lit.full_text and len(lit.full_text) > 500),
        }

    return await _get()


@function_tool
async def search_within_literature(project_id: int, query: str, max_results: int = 5) -> dict:
    """Search within the full text of papers linked to this project. Returns matching snippets with context. Use this to find specific methods, results, claims, or data within the literature."""

    @sync_to_async
    def _search():
        from main.models import Literature, Paper
        from django.db.models import Q

        try:
            paper = Paper.objects.get(project_id=project_id)
        except Paper.DoesNotExist:
            return {"results": [], "error": "No paper found"}

        literature = Literature.objects.filter(
            citations__paper=paper,
            full_text__icontains=query
        ).distinct()[:max_results]

        results = []
        for lit in literature:
            text = lit.full_text or ''
            idx = text.lower().find(query.lower())
            if idx >= 0:
                start = max(0, idx - 200)
                end = min(len(text), idx + len(query) + 200)
                snippet = text[start:end]
                results.append({
                    "literature_id": lit.pk,
                    "title": lit.title,
                    "year": lit.year,
                    "snippet": snippet,
                    "match_position": idx,
                })

        return {"query": query, "results": results, "total_matches": len(results)}

    return await _search()


def _link_literature_sync(input: LinkLiteratureInput) -> LinkLiteratureResult:
    """Create or link a Literature entry to the project's paper via a Citation.

    De-duplicates by DOI, then arXiv ID, else (title+url).
    """
    logger.info(f"link_literature(input={input})")
    project = Project.objects.get(pk=input.project_id)
    paper, _ = Paper.objects.get_or_create(project=project, defaults={'title': project.name, 'abstract': project.abstract})

    qs = Literature.objects.all()
    if input.doi:
        qs = qs.filter(doi=input.doi)
    elif input.arxiv_id:
        qs = qs.filter(arxiv_id=input.arxiv_id)
    else:
        qs = qs.filter(title=input.title, url=input.url or "")
    literature = qs.first()
    created = False
    if not literature:
        literature = Literature.objects.create(
            title=input.title,
            authors=input.authors or "",
            journal_or_publisher=input.venue or "",
            year=input.year,
            doi=input.doi or "",
            arxiv_id=input.arxiv_id or "",
            url=input.url or (input.open_access_pdf_url or ""),
            abstract=input.abstract or "",
        )
        created = True

    last_order = paper.citations.order_by('-order').first().order if paper.citations.exists() else 0
    cit = Citation.objects.create(paper=paper, literature=literature, order=last_order + 1)
    logger.info(f"link_literature(input={input}) - cit={cit}")
    return LinkLiteratureResult(literature_id=literature.id, created=created, citation_id=cit.id)


@function_tool
async def link_literature(input: LinkLiteratureInput) -> LinkLiteratureResult:
    logger.info(f"link_literature(input={input})")
    return await sync_to_async(_link_literature_sync)(input)


def _get_paper_sync(project_id: int) -> PaperModel:
    """Get the project's Paper (creating a default if missing)."""
    project = Project.objects.get(pk=project_id)
    paper, _ = Paper.objects.get_or_create(project=project, defaults={'title': project.name, 'abstract': project.abstract})
    raw = paper.content_raw or ""
    if len(raw) > 10000:
        raw = raw[:10000] + "\n% ... [truncated]"
    return PaperModel(
        id=paper.id,
        title=paper.title,
        abstract=paper.abstract or "",
        content_format=paper.content_format,
        content_raw=raw,
    )


@function_tool
async def get_paper(project_id: int) -> PaperModel:
    return await sync_to_async(_get_paper_sync)(project_id)


def _list_experiments_sync(project_id: int) -> List[ExperimentSummary]:
    sims = Simulation.objects.filter(project_id=project_id).order_by('-updated_at')
    return [ExperimentSummary(id=s.id, name=s.name, description=s.description or "", status=s.status) for s in sims]


@function_tool
async def list_experiments(project_id: int) -> List[ExperimentSummary]:
    """List simulations/experiments for a project."""
    return await sync_to_async(_list_experiments_sync)(project_id)


def _get_experiment_sync(experiment_id: int) -> ExperimentDetail:
    s = Simulation.objects.get(pk=experiment_id)
    param_items: Optional[List[KeyValue]] = None
    if s.parameters and isinstance(s.parameters, dict):
        param_items = [KeyValue(name=str(k), value=str(v)) for k, v in s.parameters.items()]
    return ExperimentDetail(id=s.id, name=s.name, description=s.description or "", code=s.code, language=s.language, parameters=param_items, status=s.status)


@function_tool
async def get_experiment(experiment_id: int) -> ExperimentDetail:
    """Get a simulation/experiment details."""
    return await sync_to_async(_get_experiment_sync)(experiment_id)


def _create_experiment_sync(input: CreateExperimentInput) -> ExperimentDetail:
    project = Project.objects.get(pk=input.project_id)
    params_dict = {item.name: item.value for item in (input.parameters or [])} if input.parameters else None
    sim = Simulation.objects.create(project=project, name=input.name, description=input.description or "", code=input.code, language=input.language, parameters=params_dict)
    return _get_experiment_sync(sim.id)


@function_tool
async def create_experiment(input: CreateExperimentInput) -> ExperimentDetail:
    """Create a simulation/experiment under a project."""
    return await sync_to_async(_create_experiment_sync)(input)


def _run_experiment_sync(experiment_id: int) -> ExperimentDetail:
    sim = Simulation.objects.get(pk=experiment_id)
    sim.status = "running"
    sim.save(update_fields=["status", "updated_at"])
    try:
        sim.run(timeout_seconds=120)
    finally:
        sim.refresh_from_db()
    return _get_experiment_sync(sim.id)


@function_tool
async def run_experiment(experiment_id: int) -> ExperimentDetail:
    """Execute a simulation/experiment and return updated details."""
    return await sync_to_async(_run_experiment_sync)(experiment_id)


def _list_hypotheses_sync(project_id: int) -> List[HypothesisModel]:
    items = Hypothesis.objects.filter(project_id=project_id).order_by('-updated_at')
    return [HypothesisModel(
        id=h.id,
        title=h.title,
        statement=h.statement,
        status=HypothesisStatus(h.status),
        evaluation_summary=h.evaluation_summary or "",
        confidence=float(h.confidence) if h.confidence is not None else None,
    ) for h in items]


@function_tool
async def list_hypotheses(project_id: int) -> List[HypothesisModel]:
    """List hypotheses for a project."""
    return await sync_to_async(_list_hypotheses_sync)(project_id)


def _create_hypothesis_sync(input: CreateHypothesisInput) -> HypothesisModel:
    project = Project.objects.get(pk=input.project_id)
    h = Hypothesis.objects.create(project=project, title=input.title, statement=input.statement, status=DjangoHypothesisStatus.PROPOSED)
    try:
        h.paper = project.paper
        h.save(update_fields=['paper'])
    except Paper.DoesNotExist:
        pass
    return HypothesisModel(id=h.id, title=h.title, statement=h.statement, status=HypothesisStatus(h.status))


@function_tool
async def create_hypothesis(input: CreateHypothesisInput) -> HypothesisModel:
    """Create a hypothesis under the project (auto-links to the project's paper if present)."""
    return await sync_to_async(_create_hypothesis_sync)(input)


def _update_hypothesis_status_sync(input: UpdateHypothesisStatusInput) -> HypothesisModel:
    h = Hypothesis.objects.get(pk=input.hypothesis_id)
    h.status = input.status.value
    h.save(update_fields=['status', 'updated_at'])
    return HypothesisModel(id=h.id, title=h.title, statement=h.statement, status=HypothesisStatus(h.status))


@function_tool
async def update_hypothesis_status(input: UpdateHypothesisStatusInput) -> HypothesisModel:
    """Update hypothesis status."""
    return await sync_to_async(_update_hypothesis_status_sync)(input)


def _create_note_sync(input: CreateNoteInput) -> NoteModel:
    project = Project.objects.get(pk=input.project_id)
    note = Note.objects.create(project=project, title=input.title, body=input.body)
    return NoteModel(id=note.id, title=note.title, body=note.body)


@function_tool
async def create_note(input: CreateNoteInput) -> NoteModel:
    """Create a project note."""
    return await sync_to_async(_create_note_sync)(input)


@function_tool
async def get_note(note_id: int) -> NoteModel:
    """Get a note by id."""
    return await sync_to_async(lambda: NoteModel(id=Note.objects.get(pk=note_id).id, title=Note.objects.get(pk=note_id).title, body=Note.objects.get(pk=note_id).body))()


def _list_notes_sync(project_id: int) -> List[NoteModel]:
    notes = Note.objects.filter(project_id=project_id).order_by('-updated_at')
    return [NoteModel(id=n.id, title=n.title, body=n.body) for n in notes]


@function_tool
async def list_notes(project_id: int) -> List[NoteModel]:
    """List notes for a project."""
    return await sync_to_async(_list_notes_sync)(project_id)


def _update_note_sync(note_id: int, title: str, body: str) -> NoteModel:
    note = Note.objects.get(pk=note_id)
    note.title = title
    note.body = body
    note.save(update_fields=['title', 'body', 'updated_at'])
    return NoteModel(id=note.id, title=note.title, body=note.body)


@function_tool
async def update_note(note_id: int, title: str, body: str) -> NoteModel:
    """Update a note's title and body."""
    return await sync_to_async(_update_note_sync)(note_id, title, body)


# ----------------------
# Environment management
# ----------------------

class PipInstallRequest(BaseModel):
    package: str = Field(description="Package spec, e.g., 'numpy' or 'pandas==2.2.1'")
    index_url: Optional[str] = Field(default=None, description="Optional custom index URL")
    upgrade: bool = Field(default=False, description="If true, pass --upgrade")
    extra_args: Optional[List[str]] = Field(default=None, description="Additional pip args if needed")


class PipInstallResult(BaseModel):
    success: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _pip_install_sync(req: PipInstallRequest) -> PipInstallResult:
    """Install a Python package into the current environment using pip.

    Executes: python -m pip install <package> [--upgrade] [--index-url URL] [extra_args...]
    """
    cmd: List[str] = [sys.executable, "-m", "pip", "install", req.package]
    if req.upgrade:
        cmd.append("--upgrade")
    if req.index_url:
        cmd.extend(["--index-url", req.index_url])
    if req.extra_args:
        # Basic sanitization: ensure list of strings
        cmd.extend([str(x) for x in req.extra_args if x is not None])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            env={**dict(), **{"PIP_DISABLE_PIP_VERSION_CHECK": "1"}},
        )
        return PipInstallResult(
            success=(proc.returncode == 0),
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )
    except subprocess.TimeoutExpired as exc:
        return PipInstallResult(success=False, returncode=124, stdout=exc.stdout or "", stderr=(exc.stderr or "") + "\nTimed out")
    except Exception as exc:
        return PipInstallResult(success=False, returncode=1, stdout="", stderr=str(exc))


@function_tool
async def pip_install_library(request: PipInstallRequest) -> PipInstallResult:
    """Install a Python library via pip in the current environment.

    Use when an experiment requires a dependency that's missing. Keep packages minimal.
    """
    logger.info(f"pip_install_library(request={request})")
    return await sync_to_async(_pip_install_sync)(request)




