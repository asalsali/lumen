from __future__ import annotations

from pydantic import BaseModel, Field
from agents import Agent


ANSWER_INSTRUCTIONS = """
You are the Hypothesis Answer Agent. Given the hypothesis, research background, and (if available) simulation outcomes, decide the status: supported, rejected, or inconclusive. Provide a concise justification grounded in evidence.
Output only the structured fields.
"""


class HypothesisAnswer(BaseModel):
    status: str = Field(description="supported | rejected | inconclusive")
    justification: str


answer_agent = Agent(
    name="hypothesis_answer",
    model="gpt-4o-mini",
        instructions=ANSWER_INSTRUCTIONS,
    output_type=HypothesisAnswer,
)


