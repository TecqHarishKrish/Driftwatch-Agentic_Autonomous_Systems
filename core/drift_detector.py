"""
=============================================================
  DriftWatch | core/drift_detector.py  [REBUILT]
  Cosine similarity + 3-step momentum + phase-aware thresholds
=============================================================
"""
import os, time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import numpy as np
from dotenv import load_dotenv

load_dotenv()

class DriftType(str, Enum):
    NONE             = "NONE"
    SCOPE_CREEP      = "SCOPE_CREEP"
    GOAL_SUBST       = "GOAL_SUBSTITUTION"
    CONTEXT_COLLAPSE = "CONTEXT_COLLAPSE"

class Phase(str, Enum):
    EXPLORE  = "EXPLORE"
    EXPLOIT  = "EXPLOIT"
    CONCLUDE = "CONCLUDE"

THRESH = {
    Phase.EXPLORE:  float(os.getenv("DRIFT_THRESHOLD_EXPLORE",  "0.20")),
    Phase.EXPLOIT:  float(os.getenv("DRIFT_THRESHOLD_EXPLOIT",  "0.28")),
    Phase.CONCLUDE: float(os.getenv("DRIFT_THRESHOLD_CONCLUDE", "0.35")),
}

@dataclass
class StepRecord:
    step_num:   int
    text:       str
    score:      float
    phase:      Phase
    threshold:  float
    drift_type: DriftType
    momentum:   float
    is_drift:   bool
    timestamp:  float = field(default_factory=time.time)

@dataclass
class GoalState:
    task:            str
    task_vector:     np.ndarray
    subgoal_texts:   List[str]
    subgoal_vectors: List[np.ndarray]


class DriftDetector:
    def __init__(self, embedder=None, verbose=True):
        from core.embedder import Embedder
        self.emb        = embedder or Embedder(verbose=False)
        self.verbose    = verbose
        self.goal_state: Optional[GoalState] = None
        self.history:    List[StepRecord]    = []

    def anchor_goal(self, task: str, subgoals: List[str]) -> GoalState:
        if self.verbose:
            print(f"[Detector] Anchoring goal: {task[:60]}...")
        task_vec     = self.emb.embed(task)
        subgoal_vecs = self.emb.embed_batch(subgoals) if subgoals else []
        self.goal_state = GoalState(
            task=task, task_vector=task_vec,
            subgoal_texts=subgoals, subgoal_vectors=subgoal_vecs,
        )
        self.history = []
        if self.verbose:
            print(f"[Detector] Anchored with {len(subgoals)} sub-goals.")
        return self.goal_state

    def evaluate_step(self, step_num: int, reasoning_text: str,
                      phase: Phase = Phase.EXPLOIT) -> StepRecord:
        if self.goal_state is None:
            raise RuntimeError("Call anchor_goal() first")

        step_vec  = self.emb.embed(reasoning_text)
        all_vecs  = [self.goal_state.task_vector] + self.goal_state.subgoal_vectors
        score     = self.emb.max_similarity(step_vec, all_vecs)
        momentum  = self._momentum()
        threshold = THRESH[phase]
        is_drift  = score < threshold
        dtype     = self._classify(score, threshold, momentum) if is_drift else DriftType.NONE

        rec = StepRecord(
            step_num=step_num, text=reasoning_text,
            score=round(score, 4), phase=phase,
            threshold=threshold, drift_type=dtype,
            momentum=round(momentum, 4), is_drift=is_drift,
        )
        self.history.append(rec)
        if self.verbose:
            bar  = "#"*int(score*20) + "-"*(20-int(score*20))
            flag = f" DRIFT:{dtype.value}" if is_drift else ""
            print(f"[Detector] Step {step_num:02d} | score={score:.3f} "
                  f"[{bar}] | thr={threshold:.2f} | mom={momentum:+.3f}{flag}")
        return rec

    def _momentum(self) -> float:
        if len(self.history) < 2:
            return 0.0
        window = self.history[-3:]
        scores = [r.score for r in window]
        deltas = [scores[i+1]-scores[i] for i in range(len(scores)-1)]
        return sum(deltas)/len(deltas)

    def _classify(self, score, threshold, momentum) -> DriftType:
        drop = threshold - score
        if score < 0.20 and momentum < -0.03:
            return DriftType.CONTEXT_COLLAPSE
        if drop > 0.15:
            return DriftType.GOAL_SUBST
        return DriftType.SCOPE_CREEP

    def is_momentum_negative(self) -> bool:
        if len(self.history) < 3:
            return False
        last3 = [r.score for r in self.history[-3:]]
        return last3[0] > last3[1] > last3[2]

    def drift_events(self) -> List[StepRecord]:
        return [r for r in self.history if r.is_drift]

    def summary(self) -> dict:
        if not self.history:
            return {}
        scores = [r.score for r in self.history]
        return {
            "total_steps":  len(self.history),
            "drift_events": len(self.drift_events()),
            "final_score":  round(scores[-1], 4),
            "avg_score":    round(sum(scores)/len(scores), 4),
            "min_score":    round(min(scores), 4),
        }
