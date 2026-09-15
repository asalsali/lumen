from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field
from agents import Agent

from ..tools import list_literature, read_literature, deep_read_literature, search_within_literature


SUMMARIZER_INSTRUCTIONS = """
You are the Literature Summarizer Agent. You will be provided the project objective. Produce a comprehensive, verbose synthesis focused on how the linked literature informs, supports, or challenges the objective.

Rules:
- Use only your tools to list and read literature content
- Do not invent papers or facts; ground claims in the provided texts
- Synthesize across sources; emphasize connections to the objective
Output only the structured fields.
"""


class ProjectFocusedSummary(BaseModel):
    combined_summary: str = Field(description="Long-form synthesis tying literature to the project objective")


literature_summarizer_agent = Agent(
    name="literature_summarizer",
    model="gpt-4o-mini",
        instructions=SUMMARIZER_INSTRUCTIONS,
    tools=[list_literature, read_literature, deep_read_literature, search_within_literature],
    output_type=ProjectFocusedSummary,
)


