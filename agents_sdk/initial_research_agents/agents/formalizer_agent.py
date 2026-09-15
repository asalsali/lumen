from __future__ import annotations

from pydantic import BaseModel, Field
from agents import Agent


FORMALIZER_INSTRUCTIONS = """
You are the Formalizer Agent. Your task is to read the current project context and produce a clearer, more rigorous problem statement and improved abstract. Keep the tone academic and precise. If the current abstract is already clear, refine it slightly for readability.

Only output the structured fields.
"""


class FormalizedAsk(BaseModel):
    improved_abstract: str = Field(description="Refined abstract reflecting a clear problem statement and objective")


formalizer_agent = Agent(
    name="formalizer",
    model="gpt-4o-mini",
    instructions=FORMALIZER_INSTRUCTIONS,
    output_type=FormalizedAsk,
)
