from __future__ import annotations

from typing import Optional
from asgiref.sync import async_to_sync, sync_to_async
from pydantic import BaseModel
from agents import Runner

from ..retry import run_with_retry

from main.models import Project, Paper

from .agents.drafting_agent import DraftSections, drafting_agent


class PaperDraftOutput(BaseModel):
    project_id: int
    paper_id: int
    updated_abstract: Optional[str] = None
    literature_review_added: bool = False


class PaperDraftServiceManager:
    """Generates an initial draft (abstract + literature review) when paper is empty/minimal."""

    def __init__(self) -> None:
        self.runner = Runner()

    async def process(self, project_id: int) -> PaperDraftOutput:
        project = await sync_to_async(Project.objects.get)(pk=project_id)
        paper, _ = await sync_to_async(Paper.objects.get_or_create)(project=project, defaults={'title': project.name, 'abstract': project.abstract})

        result = await self._run(drafting_agent, f"Project: {project.name}\nProject ID: {project.id}\nObjective: {paper.abstract or project.abstract or ''}", max_turns=50)
        sections: DraftSections = result.final_output  # type: ignore

        updated = False
        if sections.abstract and sections.abstract.strip():
            paper.abstract = sections.abstract.strip()
            updated = True
        # Append/seed literature review into content_raw
        content = paper.content_raw or ""
        content += ("\n\n# Literature Review\n\n" + sections.literature_review.strip())
        paper.content_raw = content
        await sync_to_async(paper.save)(update_fields=['abstract', 'content_raw', 'updated_at'])

        return PaperDraftOutput(
            project_id=project.id,
            paper_id=paper.id,
            updated_abstract=paper.abstract if updated else None,
            literature_review_added=True,
        )

    def run_for_project_sync(self, project_id: int) -> PaperDraftOutput:
        async def go():
            return await self.process(project_id)
        return async_to_sync(go)()

    async def _run(self, *args, **kwargs):
        """Call Runner.run with automatic retry on rate-limit errors."""
        return await run_with_retry(self.runner, *args, **kwargs)


