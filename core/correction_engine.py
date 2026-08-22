"""
=============================================================
  DriftWatch | core/correction_engine.py  [REBUILT]
  4-tier correction + checkpoint rollback + cert generation
=============================================================
"""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

class CorrectionTier(str, Enum):
    NONE     = "NONE"
    NUDGE    = "TIER_1_NUDGE"
    REINJECT = "TIER_2_REINJECT"
    ROLLBACK = "TIER_3_ROLLBACK"
    ABORT    = "TIER_4_ABORT"

@dataclass
class Checkpoint:
    step_num:    int
    score:       float
    agent_state: Dict[str, Any]
    timestamp:   float = field(default_factory=time.time)

@dataclass
class CorrectionEvent:
    step_num:       int
    tier:           CorrectionTier
    drift_type:     str
    score_before:   float
    correction_msg: str
    timestamp:      float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "step_num":       self.step_num,
            "tier":           self.tier.value,
            "drift_type":     self.drift_type,
            "score_before":   self.score_before,
            "correction_msg": self.correction_msg[:100],
        }

@dataclass
class CoherenceCertificate:
    task:                str
    final_score:         float
    avg_score:           float
    min_score:           float
    total_steps:         int
    drift_events:        int
    corrections_applied: int
    goal_maintained:     bool
    verdict:             str
    correction_log:      List[dict]

    def to_dict(self):
        return {
            "task":               self.task[:120],
            "final_score":        self.final_score,
            "avg_score":          self.avg_score,
            "min_score":          self.min_score,
            "total_steps":        self.total_steps,
            "drift_events":       self.drift_events,
            "corrections_applied":self.corrections_applied,
            "goal_maintained":    self.goal_maintained,
            "verdict":            self.verdict,
            "correction_log":     self.correction_log,
        }

    def display(self) -> str:
        bar = "=" * 58
        lines = [
            bar,
            "  DriftWatch — Coherence Certificate",
            bar,
            f"  Task      : {self.task[:65]}",
            f"  Verdict   : {self.verdict}",
            f"  Final score   : {self.final_score:.4f}",
            f"  Avg score     : {self.avg_score:.4f}",
            f"  Min score     : {self.min_score:.4f}",
            f"  Steps         : {self.total_steps}",
            f"  Drift events  : {self.drift_events}",
            f"  Corrections   : {self.corrections_applied}",
            bar,
        ]
        if self.correction_log:
            lines.append("  Corrections applied:")
            for c in self.correction_log:
                lines.append(f"    Step {c['step_num']}: {c['tier']} ({c['drift_type']}) "
                              f"score={c['score_before']:.3f}")
            lines.append(bar)
        return "\n".join(lines)


class CorrectionEngine:
    MAX_RETRIES = 2

    def __init__(self, task: str, verbose=True):
        self.task        = task
        self.verbose     = verbose
        self.checkpoints: List[Checkpoint]     = []
        self.corrections: List[CorrectionEvent] = []
        self.retry_map:   Dict[int, int]        = {}
        self._aborted     = False

    def save_checkpoint(self, step_num, score, agent_state):
        self.checkpoints.append(Checkpoint(step_num, score, dict(agent_state)))
        if self.verbose:
            print(f"[Correction] Checkpoint saved step={step_num} score={score:.3f}")

    def last_checkpoint(self) -> Optional[Checkpoint]:
        return self.checkpoints[-1] if self.checkpoints else None

    def correct(self, step_num, score, threshold, drift_type, context="") -> Dict:
        if self._aborted:
            return self._make_abort(step_num, score, drift_type, "Already aborted")

        depth = max(0.0, threshold - score)
        if   depth < 0.08: tier = CorrectionTier.NUDGE
        elif depth < 0.18: tier = CorrectionTier.REINJECT
        elif depth < 0.30: tier = CorrectionTier.ROLLBACK
        else:              tier = CorrectionTier.ABORT

        # Budget check
        cp = self.last_checkpoint()
        if cp:
            retries = self.retry_map.get(cp.step_num, 0)
            if retries >= self.MAX_RETRIES:
                tiers = [CorrectionTier.NUDGE, CorrectionTier.REINJECT,
                         CorrectionTier.ROLLBACK, CorrectionTier.ABORT]
                idx   = tiers.index(tier)
                tier  = tiers[min(idx+1, 3)]

        if tier == CorrectionTier.NUDGE:
            result = self._nudge(step_num, score, drift_type, context)
        elif tier == CorrectionTier.REINJECT:
            result = self._reinject(step_num, score, drift_type, context)
        elif tier == CorrectionTier.ROLLBACK:
            result = self._rollback(step_num, score, drift_type)
        else:
            result = self._make_abort(step_num, score, drift_type, "Drift too severe")

        ev = CorrectionEvent(step_num, tier, drift_type, score, str(result["correction_msg"]))
        self.corrections.append(ev)
        if cp:
            self.retry_map[cp.step_num] = self.retry_map.get(cp.step_num, 0) + 1

        if self.verbose:
            print(f"[Correction] {tier.value} applied | step={step_num} score={score:.3f}")
        return result

    def _nudge(self, sn, score, dtype, ctx):
        msg = (f"\n[REMINDER] Your main task is: {self.task}\n"
               "Stay focused on this goal only.")
        return {"tier": CorrectionTier.NUDGE, "new_context": ctx+msg,
                "should_rollback": False, "should_abort": False,
                "correction_msg": f"Soft nudge: goal reminder appended"}

    def _reinject(self, sn, score, dtype, ctx):
        msg = (f"\n[CRITICAL] Return to your ONLY task: {self.task}\n"
               f"Detected drift: {dtype}. Ignore tangential content. "
               f"Next step must directly address the original task.")
        return {"tier": CorrectionTier.REINJECT, "new_context": ctx+msg,
                "should_rollback": False, "should_abort": False,
                "correction_msg": f"Goal re-injected: drift={dtype}"}

    def _rollback(self, sn, score, dtype):
        cp = self.last_checkpoint()
        if cp is None:
            return self._make_abort(sn, score, dtype, "No checkpoint for rollback")
        msg = (f"\n[ROLLBACK] Restored to step {cp.step_num} "
               f"(score={cp.score:.3f}). Drift was: {dtype}. "
               f"Main task: {self.task}")
        return {"tier": CorrectionTier.ROLLBACK, "new_context": msg,
                "should_rollback": True, "should_abort": False,
                "rollback_to_step": cp.step_num, "rollback_state": cp.agent_state,
                "correction_msg": f"Rollback to step {cp.step_num}"}

    def _make_abort(self, sn, score, dtype, reason):
        self._aborted = True
        diagnosis = (f"Abort at step {sn}. Reason: {reason}. "
                     f"Drift: {dtype}. Score: {score:.3f}. "
                     f"Task: {self.task[:100]}")
        return {"tier": CorrectionTier.ABORT, "new_context": "",
                "should_rollback": False, "should_abort": True,
                "correction_msg": f"ABORT: {reason}", "diagnosis": diagnosis}

    def generate_certificate(self, scores, total_steps, drift_count) -> CoherenceCertificate:
        if not scores:
            scores = [0.0]
        final = scores[-1]
        avg   = sum(scores)/len(scores)
        mn    = min(scores)
        n_cor = len(self.corrections)
        # Judge on AVERAGE score + corrections, not final alone
        # Demo shows drift at step 3 then recovery — avg is the honest metric
        if avg >= 0.60 and drift_count == 0:
            verdict, maintained = "VERIFIED", True
        elif avg >= 0.45 or (n_cor >= 1 and final >= 0.25):
            verdict, maintained = "VERIFIED_WITH_CORRECTIONS", True
        elif avg >= 0.30:
            verdict, maintained = "PARTIALLY_VERIFIED", False
        else:
            verdict, maintained = "FAILED", False
        return CoherenceCertificate(
            task=self.task, final_score=round(final,4),
            avg_score=round(avg,4), min_score=round(mn,4),
            total_steps=total_steps, drift_events=drift_count,
            corrections_applied=n_cor, goal_maintained=maintained,
            verdict=verdict, correction_log=[c.to_dict() for c in self.corrections],
        )

    def summary(self):
        return {
            "corrections_total": len(self.corrections),
            "checkpoints_saved": len(self.checkpoints),
            "aborted":           self._aborted,
        }
