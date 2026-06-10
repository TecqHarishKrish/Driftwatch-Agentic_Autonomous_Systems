"""
=============================================================
  DriftWatch | agent/step_interceptor.py  [REBUILT]
  Hooks into every agent step — calls detector, pushes events.
=============================================================
"""
import time
from dataclasses import dataclass, field
from typing import Optional, List
from core.drift_detector import DriftDetector, Phase, DriftType
from agent.reasoning_extractor import ReasoningExtractor
from core.embedder import Embedder

@dataclass
class InterceptorEvent:
    step_num:          int
    phase:             str
    score:             float
    threshold:         float
    drift_detected:    bool
    drift_type:        str
    momentum:          float
    correction_needed: bool
    focus:             str
    goal_link:         str
    timestamp:         float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "step_num":          self.step_num,
            "phase":             self.phase,
            "score":             round(self.score, 4),
            "threshold":         round(self.threshold, 4),
            "drift_detected":    self.drift_detected,
            "drift_type":        self.drift_type,
            "momentum":          round(self.momentum, 4),
            "correction_needed": self.correction_needed,
            "focus":             self.focus[:120],
            "goal_link":         self.goal_link[:120],
            "timestamp":         self.timestamp,
        }

# Phase map for 5-step agent
PHASE_MAP = {1: Phase.EXPLORE, 2: Phase.EXPLORE,
             3: Phase.EXPLOIT,  4: Phase.EXPLOIT, 5: Phase.CONCLUDE}

class StepInterceptor:
    def __init__(self, detector=None, extractor=None,
                 event_queue=None, verbose=True):
        emb = Embedder(verbose=False)
        self.detector    = detector  or DriftDetector(embedder=emb, verbose=verbose)
        self.extractor   = extractor or ReasoningExtractor(embedder=emb)
        self.event_queue = event_queue
        self.verbose     = verbose
        self.events: List[InterceptorEvent] = []

    def anchor(self, task: str, subgoals: List[str]):
        self.detector.anchor_goal(task, subgoals)

    def intercept(self, step_num: int, step_output: dict) -> InterceptorEvent:
        trace   = self.extractor.extract(step_num, step_output)
        phase   = PHASE_MAP.get(step_num, Phase.CONCLUDE)
        record  = self.detector.evaluate_step(
            step_num, trace.composite_text, phase)
        event   = InterceptorEvent(
            step_num=step_num, phase=phase.value,
            score=record.score, threshold=record.threshold,
            drift_detected=record.is_drift,
            drift_type=record.drift_type.value,
            momentum=record.momentum,
            correction_needed=record.is_drift or self.detector.is_momentum_negative(),
            focus=trace.current_focus, goal_link=trace.connection_to_goal,
        )
        self.events.append(event)
        if self.event_queue is not None:
            self.event_queue.append(event.to_dict())
        if self.verbose:
            tag = "CORRECTION NEEDED" if event.correction_needed else "clean"
            print(f"[Interceptor] Step {step_num:02d} score={event.score:.3f} | {tag}")
        return event

    def score_history(self) -> List[float]:
        return [e.score for e in self.events]

    def threshold_history(self) -> List[float]:
        return [e.threshold for e in self.events]

    def get_drift_events(self) -> List[InterceptorEvent]:
        return [e for e in self.events if e.drift_detected]

    def get_all_events(self) -> List[dict]:
        return [e.to_dict() for e in self.events]
