from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field
from agents import Agent

from ..tools import (
    list_experiments,
    list_literature,
    create_hypothesis,
    update_hypothesis_status,
    HypothesisModel,
)


HYPOTHESIZER_INSTRUCTIONS = """
You are the Hypothesizer Agent. Your job is to propose high-quality, testable hypotheses that would satisfy the project's objective.

Use your tools to inspect available experiments and linked literature. Then, create hypotheses following these rigorous standards:

Requirements for each hypothesis:
- It must be FALSIFIABLE and SPECIFIC: state a clear, measurable prediction rather than a vague directional claim. Bad: "X may improve Y." Good: "Applying method X to dataset Z will improve metric Y by at least 10% compared to baseline B."
- It must REFERENCE specific findings from the linked literature (e.g., "Building on Smith et al.'s finding that ..., we hypothesize that ...").
- It must specify what EVIDENCE would support it and what evidence would REJECT it (e.g., "Supported if p < 0.05 for effect E; rejected if no significant difference is observed or if the effect reverses.").

Quantity and coverage:
- Propose 3-7 hypotheses that cover DIFFERENT aspects of the research question (e.g., mechanism, scope, boundary conditions, alternative explanations).
- Include at least one CONTRARIAN or ALTERNATIVE hypothesis that challenges the dominant direction suggested by the literature. This ensures the research is not confirmation-biased.

When appropriate, set statuses after creation only if there is immediate strong evidence (otherwise leave as PROPOSED).
Output only the structured fields.
"""


class HypothesesOutput(BaseModel):
    created: List[HypothesisModel] = Field(default_factory=list, description="Hypotheses created during this run")


hypothesizer_agent = Agent(
    name="hypothesizer",
    model="gpt-4o-mini",
        instructions=HYPOTHESIZER_INSTRUCTIONS,
    tools=[list_experiments, list_literature, create_hypothesis, update_hypothesis_status],
    output_type=HypothesesOutput,
)


