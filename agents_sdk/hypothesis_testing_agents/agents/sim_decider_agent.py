from __future__ import annotations

from pydantic import BaseModel, Field
from agents import Agent


SIM_DECIDER_INSTRUCTIONS = """
You are the Simulation Decider Agent. Given a hypothesis and context, decide if a Python-based simulation can help test it.
Output only a boolean and a short rationale.
"""


class SimulationDecision(BaseModel):
    needed: bool = Field(description="True if a Python simulation should be created/executed")
    rationale: str = Field(description="Why this decision was made")


sim_decider_agent = Agent(
    name="simulation_decider",
    model="gpt-4o-mini",
        instructions=SIM_DECIDER_INSTRUCTIONS,
    output_type=SimulationDecision,
)


