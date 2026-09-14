from __future__ import annotations

from typing import List
import asyncio
from asgiref.sync import async_to_sync, sync_to_async
from pydantic import BaseModel
from agents import Runner

from ..retry import run_with_retry

from main.models import Project, Hypothesis, HypothesisStatus as DjangoHypothesisStatus

from .agents.research_agent import research_agent, HypothesisResearch
from .agents.sim_decider_agent import sim_decider_agent, SimulationDecision
from .agents.simulation_agent import simulation_agent, SimulationResult
from .agents.answer_agent import answer_agent, HypothesisAnswer
from ..initial_research_agents.utilities import (
    list_hypotheses,
    update_hypothesis_status,
    create_experiment,
    run_experiment,
    get_experiment,
)


class HypothesisTestResult(BaseModel):
    hypothesis_id: int
    status: str
    justification: str


class HypothesisTestingOutput(BaseModel):
    project_id: int
    results: List[HypothesisTestResult]


class HypothesisTestingServiceManager:
    """Sequentially evaluates each hypothesis: research → decide simulation → (optionally) simulate → answer."""

    def __init__(self) -> None:
        self.runner = Runner()

    async def process(self, project_id: int) -> HypothesisTestingOutput:
        project = await sync_to_async(Project.objects.get)(pk=project_id)
        existing = await list_hypotheses(project.id)

        results: List[HypothesisTestResult] = []
        batch_size = 8
        for i in range(0, len(existing), batch_size):
            batch = existing[i:i + batch_size]
            batch_results = await asyncio.gather(*[
                self._process_hypothesis(project, h) for h in batch
            ])
            results.extend(batch_results)

        return HypothesisTestingOutput(project_id=project.id, results=results)

    async def _run_sim(self, experiment_id: int) -> SimulationResult:
        # Use utilities to execute and fetch experiment details
        await run_experiment(experiment_id)
        det = await get_experiment(experiment_id)
        return SimulationResult(experiment_id=experiment_id, status=det.status, stdout=None)

    def run_for_project_sync(self, project_id: int) -> HypothesisTestingOutput:
        async def go():
            return await self.process(project_id)
        return async_to_sync(go)()

    async def _run(self, *args, **kwargs):
        """Call Runner.run with automatic retry on rate-limit errors."""
        return await run_with_retry(self.runner, *args, **kwargs)

    async def _process_hypothesis(self, project: Project, h) -> HypothesisTestResult:
        # 1) Research background
        research_result = await self._run(
            research_agent,
            f"Project ID: {project.id}\nHypothesis: {h.title}\n{h.statement}",
            max_turns=50,
        )
        research: HypothesisResearch = research_result.final_output  # type: ignore

        # 2) Simulation decision
        decider_result = await self._run(
            sim_decider_agent,
            f"Project ID: {project.id}\nHypothesis: {h.title}\n{h.statement}\nBackground:\n{research.background_summary}",
            max_turns=50,
        )
        decision: SimulationDecision = decider_result.final_output  # type: ignore

        sim_out: SimulationResult | None = None
        if decision.needed:
            # Create and run a simple placeholder experiment
            sim_prompt = f"# Test for: {h.title}\nprint('Test placeholder')"
            exp = await create_experiment(project_id=project.id, name=f"AutoSim: {h.title}", code=sim_prompt)
            sim_out = await self._run_sim(exp.id)

        # 3) Answer hypothesis
        combined_input = "\n".join([
            f"Project ID: {project.id}",
            f"Hypothesis: {h.title}",
            h.statement,
            "",
            "Background:",
            research.background_summary,
            "",
            f"Simulation: {sim_out.status if sim_out else 'not required'}",
        ])
        answer_result = await self._run(answer_agent, combined_input, max_turns=50)
        answer: HypothesisAnswer = answer_result.final_output  # type: ignore

        # Update status in DB
        target_status = answer.status.lower()
        if target_status not in {"supported", "rejected", "inconclusive"}:
            target_status = "inconclusive"
        await update_hypothesis_status(hypothesis_id=h.id, status=target_status)

        return HypothesisTestResult(
            hypothesis_id=h.id,
            status=target_status,
            justification=answer.justification,
        )


