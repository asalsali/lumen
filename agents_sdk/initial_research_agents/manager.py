from __future__ import annotations

import random
from typing import List, Optional

from asgiref.sync import async_to_sync, sync_to_async
from pydantic import BaseModel, Field

from agents import Runner

from ..retry import run_with_retry

from main.models import Project, Paper, Note

from .tools import (
    PaperModel,
    ExperimentSummary,
    HypothesisModel,
)
from .utilities import (
    list_experiments,
    list_literature,
)
from .agents.formalizer_agent import FormalizedAsk, formalizer_agent
from .agents.literature_reviewer_agent import LiteratureReviewOutcome, literature_reviewer_agent
from .agents.literature_summarizer_agent import ProjectFocusedSummary, literature_summarizer_agent
from .agents.hypothesizer_agent import HypothesesOutput, hypothesizer_agent

import logging

logger = logging.getLogger(__name__)


class InitialResearchOutput(BaseModel):
    project_id: int
    paper_id: int
    improved_abstract: Optional[str] = None
    literature_summary_note_id: Optional[int] = None
    created_hypotheses: List[HypothesisModel] = Field(default_factory=list)


class InitialResearchServiceManager:
    """Orchestrates the initial research workflow for a project.

    Steps:
    1. Formalize/Improve the abstract and objectives
    2. Literature review with search + linking
    3. Literature summarization focused on project goal (saved as Note)
    4. Hypothesis generation using available tools
    """

    def __init__(self) -> None:
        self.runner = Runner()

    async def process(self, project_id: int) -> InitialResearchOutput:
        logger.info(f"InitialResearchServiceManager.process(project_id={project_id})")
        project = await sync_to_async(Project.objects.get)(pk=project_id)
        paper, _ = await sync_to_async(Paper.objects.get_or_create)(
            project=project,
            defaults={'title': project.name, 'abstract': project.abstract},
        )
        logger.info(f"paper and project retrieved")
        # Gather context summaries
        experiments: List[ExperimentSummary] = await list_experiments(project_id)
        literature_meta = await list_literature(project_id)
        logger.info(f"experiments and literature_meta retrieved {experiments} {literature_meta}")
        # Prepare common context snippets
        experiments_text = (
            "\n".join([f"- {e.name} (status={e.status})" for e in experiments])
            if experiments else "None available."
        )
        literature_text = (
            "\n".join([
                f"- {getattr(lm, 'title', 'Untitled')}{(' (' + str(getattr(lm, 'year', None)) + ')') if getattr(lm, 'year', None) else ''}"
                for lm in (literature_meta or [])
            ]) if literature_meta else "None linked yet."
        )

        # Step 1: Formalize
        formalizer_input = f"""
Project: {project.name}
Project ID: {project.id}

Paper title: {paper.title}

Current abstract:
{paper.abstract or ''}

Experiments overview:
{experiments_text}

Linked literature (title / optional year):
{literature_text}

Task: Improve and formalize the research ask and abstract.
- Preserve factual content; do not invent new results or sources.
- Clarify the objective, scope, and expected outcomes.
- Make objectives measurable when possible.
- Keep the tone concise and scientifically neutral.
"""
        logger.info(f"running formalizer agent")
        formalizer_result = await self._run(
            formalizer_agent,
            formalizer_input,
            max_turns=50,
        )
        formalized: FormalizedAsk = formalizer_result.final_output  # type: ignore
        logger.info(f"formalizer agent result {formalizer_result}")
        logger.info(f"[STEP] Formalizer improved abstract: {(formalized.improved_abstract or '')[:100]}")

        improved_abstract = (formalized.improved_abstract or '').strip()
        if improved_abstract and improved_abstract != (paper.abstract or '').strip():
            paper.abstract = improved_abstract
            logger.info(f"Updating paper abstract")
            await sync_to_async(paper.save)(update_fields=['abstract', 'updated_at'])
            logger.info(f"paper abstract updated")

        # Step 2: Literature review (agent uses tools to search/link)
        reviewer_input = f"""
Project: {project.name}
Project ID: {project.id}

Formalized ask / objective:
{(formalized.improved_abstract or paper.abstract or '').strip()}

Previously linked literature (title / optional year):
{literature_text}

Task: Use your available tools to discover and, when appropriate, link relevant literature to this project.
- Prioritize recent, high-quality, and directly relevant sources.
- Avoid duplicate links; only add what strengthens the project objective.
- If a found source is not accessible by reading tools, skip linking it.
- When linking, ensure the link is associated with Project ID {project.id}.
"""
        logger.info("[STEP] Starting literature search across arXiv, Semantic Scholar, DOAJ, OpenAlex")
        logger.info(f"running literature reviewer agent")
        reviewer_result = await self._run(literature_reviewer_agent, reviewer_input, max_turns=50)
        logger.info(f"literature reviewer agent result {reviewer_result}")
        review_output: LiteratureReviewOutcome = reviewer_result.final_output  # type: ignore
        logger.info(f"[STEP] Found and linked {len(getattr(review_output, 'selected', []))} papers")

        # Refresh literature after potential linking
        literature_meta = await list_literature(project_id)
        logger.info(f"literature meta updated {literature_meta}")
        # Step 3: Literature summarization (agent reads via tools)
        literature_text_after_review = (
            "\n".join([
                f"- {getattr(lm, 'title', 'Untitled')}{(' (' + str(getattr(lm, 'year', None)) + ')') if getattr(lm, 'year', None) else ''}"
                for lm in (literature_meta or [])
            ]) if literature_meta else "None linked yet."
        )
        summarizer_input = f"""
Project: {project.name}
Project ID: {project.id}

Objective:
{(formalized.improved_abstract or paper.abstract or '').strip()}

Linked literature to consider (title / optional year):
{literature_text_after_review}

Task: Read accessible linked sources using your tools and produce a focused synthesis.
- Explain how each source connects to the objective.
- Synthesize agreements, disagreements, and gaps relevant to the project.
- Do not invent sources; cite by title/year only when you have tool-derived content.
- Be concise and structured.
"""
        logger.info("[STEP] Synthesizing literature findings")
        logger.info(f"running literature summarizer agent")
        summarizer_result = await self._run(literature_summarizer_agent, summarizer_input, max_turns=50)
        logger.info(f"literature summarizer agent result {summarizer_result}")
        summary: ProjectFocusedSummary = summarizer_result.final_output  # type: ignore
        logger.info(f"[STEP] Created literature summary note ({len(summary.combined_summary)} chars)")

        # Save as Note with a 4-digit id suffix in title
        note_title = f"Literature Summary {random.randint(1000, 9999)}"
        note = await sync_to_async(Note.objects.create)(project=project, title=note_title, body=summary.combined_summary)
        logger.info(f"note created {note}")
        # Step 4: Hypothesis generation (agent can create hypotheses via tools)
        experiments_text_after = (
            "\n".join([f"- {e.name} (status={e.status})" for e in experiments])
            if experiments else "None available."
        )
        hypothesizer_input = f"""
Project: {project.name}
Project ID: {project.id}

Objective:
{(formalized.improved_abstract or paper.abstract or '').strip()}

Available experiments:
{experiments_text_after}

Task: Propose a small set of high-quality, testable hypotheses that would advance the objective.
- Each hypothesis should be specific, falsifiable, and scoped to available capabilities.
- Where possible, ground each hypothesis in linked literature or experiment context.
- Use your tools to create hypotheses in the system; prioritize quality over quantity.
"""
        logger.info("[STEP] Generating research hypotheses")
        logger.info(f"running hypothesizer agent")
        hypotheses_result = await self._run(hypothesizer_agent, hypothesizer_input, max_turns=50)
        logger.info(f"hypothesizer agent result {hypotheses_result}")
        hypotheses_output: HypothesesOutput = hypotheses_result.final_output  # type: ignore
        logger.info(f"[STEP] Proposed {len(hypotheses_output.created or [])} hypotheses")

        # Return snapshot of created/updated items
        return InitialResearchOutput(
            project_id=project.id,
            paper_id=paper.id,
            improved_abstract=paper.abstract or None,
            literature_summary_note_id=note.id,
            created_hypotheses=hypotheses_output.created or [],
        )

    def run_for_project_sync(self, project_id: int) -> InitialResearchOutput:
        """Sync wrapper for Django contexts."""

        async def go():
            return await self.process(project_id)

        return async_to_sync(go)()

    async def _run(self, *args, **kwargs):
        """Call Runner.run with automatic retry on rate-limit errors."""
        return await run_with_retry(self.runner, *args, **kwargs)

    


