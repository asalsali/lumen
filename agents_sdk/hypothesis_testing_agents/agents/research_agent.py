from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field
from agents import Agent, ModelSettings

from ...initial_research_agents.tools import literature_search, list_literature, read_literature, deep_read_literature, search_within_literature


RESEARCHER_INSTRUCTIONS = """
You are the Hypothesis Research Agent. For a given hypothesis, gather comprehensive background information to evaluate it rigorously.

Research process:
- Use `literature_search` to find relevant papers, then use `deep_read_literature` to thoroughly examine the most relevant ones (not just abstracts).
- Use `search_within_literature` to locate specific claims, methods, or data points within already-linked papers.
- Search for BOTH supporting AND contradicting evidence. A balanced review requires understanding why the hypothesis might be wrong, not just why it might be right.
- Identify the methodological approaches used in similar studies (experimental designs, statistical tests, datasets, baselines).
- Note concrete details from the literature: sample sizes, effect sizes, statistical methods, confidence intervals, and key quantitative findings.

Output:
- Produce a concise but thorough background summary that covers: (1) evidence supporting the hypothesis, (2) evidence contradicting or complicating it, (3) methodological precedents, and (4) gaps in the existing literature.
- Avoid fabricating sources. Only cite papers you have actually retrieved and read via tools.
"""


class HypothesisResearch(BaseModel):
    background_summary: str = Field(description="Synthesis of evidence relevant to the hypothesis")


research_agent = Agent(
    name="hypothesis_researcher",
    model="gpt-5",
    model_settings=ModelSettings(
        reasoning={
            "effort": "high"
        }
    ),
    instructions=RESEARCHER_INSTRUCTIONS,
    tools=[literature_search, list_literature, read_literature, deep_read_literature, search_within_literature],
    output_type=HypothesisResearch,
)


