from pydantic import BaseModel
from typing import List


class AgentStep(BaseModel):
    step: int
    tool: str
    description: str


class AgentPlan(BaseModel):
    steps: List[AgentStep]
