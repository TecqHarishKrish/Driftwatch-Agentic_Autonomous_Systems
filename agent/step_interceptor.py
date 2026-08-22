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

    def intercept(self, step_num: int, step_output: dict, total_steps: int = 5) -> InterceptorEvent:
        trace   = self.extractor.extract(step_num, step_output)
        if total_steps <= 1:
            phase = Phase.CONCLUDE
        elif step_num == total_steps:
            phase = Phase.CONCLUDE
        else:
            explore_boundary = max(1, int(total_steps * 0.4))
            exploit_boundary = max(explore_boundary + 1, int(total_steps * 0.8))
            if step_num <= explore_boundary:
                phase = Phase.EXPLORE
            elif step_num <= exploit_boundary:
                phase = Phase.EXPLOIT
            else:
                phase = Phase.CONCLUDE

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

from core.human_readable import build_explanation, get_severity_label
from core.intervention_gate import request_user_decision
from core.workflow_session import WorkflowSession, CorrectionEvent, CorrectionStatus

def dispatch_correction_with_gate(tier, drift_type, session_id,
                                   step_number, sse_push_fn=None):
    """
    Wraps existing correction dispatch with human-in-the-loop gate
    for Tier 3 and Tier 4 corrections.
    sse_push_fn: callable that pushes an SSE event to the dashboard.
    """
    explanation = build_explanation(tier, drift_type)
    severity    = get_severity_label(tier)

    if tier <= 2:
        # Auto-apply: existing correction logic runs unchanged
        status = CorrectionStatus.AUTO_APPLIED
        if sse_push_fn:
            sse_push_fn("correction_applied", {
                "tier": tier,
                "drift_type": drift_type,
                "message": explanation,
                "severity": severity,
                "step": step_number
            })
    else:
        # Gate: push pending event, block until user decides
        if sse_push_fn:
            sse_push_fn("correction_pending", {
                "tier": tier,
                "drift_type": drift_type,
                "message": explanation,
                "severity": severity,
                "step": step_number,
                "session_id": session_id
            })
        decision = request_user_decision(session_id, {
            "tier": tier,
            "drift_type": drift_type,
            "message": explanation,
            "step": step_number
        })
        if decision == "approve":
            status = CorrectionStatus.USER_APPROVED
        else:
            status = CorrectionStatus.USER_REJECTED
            # User rejected — log and return, do not apply correction
            _log_correction_event(
                session_id, step_number, tier, drift_type,
                "user_rejected_no_correction", status, decision
            )
            if sse_push_fn:
                sse_push_fn("correction_rejected", {
                    "tier": tier,
                    "drift_type": drift_type,
                    "step": step_number,
                    "message": "User chose to continue without correction."
                })
            return "rejected"

    _log_correction_event(
        session_id, step_number, tier, drift_type,
        explanation, status,
        "auto" if tier <= 2 else decision
    )
    return "applied"

def _log_correction_event(session_id, step_number, tier, drift_type,
                           correction_applied, status, user_decision):
    try:
        ws_data = WorkflowSession.load(session_id)
        event = {
            "step_number": step_number,
            "tier": tier,
            "drift_type": drift_type,
            "correction_applied": correction_applied,
            "status": status.value if hasattr(status, 'value') else str(status),
            "user_decision": user_decision,
            "timestamp": __import__('time').time()
        }
        ws_data.setdefault("drift_events", []).append(event)
        from core.workflow_session import save_session_dict
        save_session_dict(session_id, ws_data)
    except Exception as e:
        print(f"[DriftWatch] Warning: Could not log correction event: {e}")

