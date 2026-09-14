from __future__ import annotations

from pydantic import BaseModel, Field
from agents import Agent, ModelSettings

from ...initial_research_agents.tools import list_literature, read_literature, list_hypotheses, get_paper


DRAFTING_INSTRUCTIONS = """
You are the Initial Drafting Agent. Assume there is little to no paper content.
Using the project objective, available literature (read abstracts/text via tools), and current hypotheses, produce a draft consisting of:
- Improved abstract
- Literature Review section (synthesized from the summaries)

Do not fabricate sources. Focus on clarity, academic tone, and grounding claims in the linked literature.
Output only the structured fields.
"""


class DraftSections(BaseModel):
    abstract: str = Field(description="Improved abstract text")
    literature_review: str = Field(description="Draft Literature Review section")


drafting_agent = Agent(
    name="initial_drafting",
    model="gpt-5",
    model_settings=ModelSettings(
        reasoning={
            "effort": "high"
        }
    ),
    instructions=DRAFTING_INSTRUCTIONS,
    tools=[list_literature, read_literature, list_hypotheses, get_paper],
    output_type=DraftSections,
)


