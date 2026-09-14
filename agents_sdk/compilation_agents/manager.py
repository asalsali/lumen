from __future__ import annotations

from typing import List
from asgiref.sync import async_to_sync, sync_to_async
from pydantic import BaseModel
from agents import Runner

from ..retry import run_with_retry

from main.models import Project, Paper, PaperContentFormat

from .agents.compilation_agent import compilation_agent, FullLatexPaper

import logging
logger = logging.getLogger(__name__)

class CompilationOutput(BaseModel):
    project_id: int
    paper_id: int
    applied_diffs: int
    changed: bool = False


class CompilationServiceManager:
    """Generates the full LaTeX manuscript for the project's paper using the compilation agent."""

    def __init__(self) -> None:
        self.runner = Runner()

    async def process(self, project_id: int) -> CompilationOutput:
        logger.info(f"CompilationServiceManager.process(project_id={project_id})")
        project = await sync_to_async(Project.objects.get)(pk=project_id)
        paper, _ = await sync_to_async(Paper.objects.get_or_create)(project=project, defaults={'title': project.name, 'abstract': project.abstract})

        try:
            result = await self._run(compilation_agent, f"Project: {project.name}\nProject ID: {project.id}", max_turns=50)
        except Exception as e:
            logger.error(f"CompilationServiceManager.process(error={e})")
            raise e
        logger.info(f"CompilationServiceManager.process(result={result})")
        latex_doc: FullLatexPaper = result.final_output  # type: ignore

        generated = (latex_doc.latex or '').strip()
        if not generated:
            logger.info(f"CompilationServiceManager.process(no content generated)")
            return CompilationOutput(project_id=project.id, paper_id=paper.id, applied_diffs=0, changed=False)

        current = paper.content_raw or ""
        changed = (generated != current)
        applied = 1 if changed else 0
        if changed:
            logger.info(f"CompilationServiceManager.process(applying new LaTeX)")
            paper.content_raw = generated
            paper.content_format = PaperContentFormat.LATEX
            await sync_to_async(paper.save)(update_fields=['content_raw', 'content_format', 'updated_at'])
        else:
            logger.info(f"CompilationServiceManager.process(no change to content)")
        logger.info(f"CompilationServiceManager.process(done)")
        return CompilationOutput(project_id=project.id, paper_id=paper.id, applied_diffs=applied, changed=changed)

    def run_for_project_sync(self, project_id: int) -> CompilationOutput:
        async def go():
            return await self.process(project_id)
        return async_to_sync(go)()

    async def _run(self, *args, **kwargs):
        """Call Runner.run with automatic retry on rate-limit errors."""
        return await run_with_retry(self.runner, *args, **kwargs)


