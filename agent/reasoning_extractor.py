"""
=============================================================
  DriftWatch | agent/reasoning_extractor.py  [REBUILT]
=============================================================
"""
import numpy as np
from dataclasses import dataclass
from typing import Optional

@dataclass
class ReasoningTrace:
    step_num:           int
    current_focus:      str
    connection_to_goal: str
    next_action:        str
    step_output:        str
    composite_text:     str
    composite_vector:   Optional[np.ndarray] = None

class ReasoningExtractor:
    """
    Weights: connection_to_goal (60%) + current_focus (25%) + next_action (15%)
    """
    def __init__(self, embedder=None):
        from core.embedder import Embedder
        self.emb = embedder or Embedder(verbose=False)

    def extract(self, step_num: int, agent_output: dict) -> ReasoningTrace:
        focus   = str(agent_output.get("current_focus",     "No focus"))
        connect = str(agent_output.get("connection_to_goal","No connection"))
        action  = str(agent_output.get("next_action",       "No action"))
        output  = str(agent_output.get("step_output",       "No output"))
        # Weight: repeat connection 3x, focus 2x, action 1x
        composite = f"{connect} {connect} {connect} {focus} {focus} {action}"
        vec = self.emb.embed(composite)
        return ReasoningTrace(
            step_num=step_num, current_focus=focus,
            connection_to_goal=connect, next_action=action,
            step_output=output, composite_text=composite,
            composite_vector=vec,
        )
