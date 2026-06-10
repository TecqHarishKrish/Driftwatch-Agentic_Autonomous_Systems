"""
=============================================================
  DriftWatch | core/drift_classifier.py
  DAY 2 — FILE 3
  Purpose : Fine-grained drift type classification
            Extends the rule-based classifier in drift_detector
            with keyword signals from reasoning text.
  Run self-test : python -m core.drift_classifier
=============================================================
"""
from core.drift_detector import DriftType


# Keywords strongly associated with each drift type
SCOPE_CREEP_SIGNALS = [
    "additional", "also", "furthermore", "expanding", "broader",
    "bonus", "extra", "include also", "related to", "tangentially",
    "while we are at it", "additionally", "side note",
]

GOAL_SUBSTITUTION_SIGNALS = [
    "instead", "rather than", "pivot", "shift focus", "new direction",
    "reframe", "actually", "turns out", "better approach",
    "more relevant", "changed", "switching to", "moving to",
]

CONTEXT_COLLAPSE_SIGNALS = [
    "forget", "ignore", "disregard", "starting over", "from scratch",
    "unrelated", "different topic", "new task", "completely different",
    "nothing to do with", "not relevant",
]


def classify_drift_type(
    score: float,
    threshold: float,
    momentum: float,
    reasoning_text: str,
) -> DriftType:
    """
    Classify the type of goal drift using score depth + keyword signals.

    Priority order:
      1. Context Collapse (most severe — very low score + strong signals)
      2. Goal Substitution (medium severity — clear directional change)
      3. Scope Creep (least severe — expanding beyond scope)

    Args:
        score          : Current coherence score (0–1)
        threshold      : Threshold that was breached
        momentum       : Rate of score change (negative = getting worse)
        reasoning_text : The agent's reasoning output for this step

    Returns:
        DriftType enum value
    """
    if score >= threshold:
        return DriftType.NONE

    text_lower = reasoning_text.lower()
    drop = threshold - score

    # Count keyword signals per type
    collapse_hits  = sum(1 for kw in CONTEXT_COLLAPSE_SIGNALS  if kw in text_lower)
    subst_hits     = sum(1 for kw in GOAL_SUBSTITUTION_SIGNALS if kw in text_lower)
    creep_hits     = sum(1 for kw in SCOPE_CREEP_SIGNALS       if kw in text_lower)

    # Context Collapse: severe score drop + negative momentum + collapse keywords
    if score < 0.40 and momentum < -0.04 and collapse_hits >= 1:
        return DriftType.CONTEXT_COLLAPSE
    if score < 0.35:
        return DriftType.CONTEXT_COLLAPSE

    # Goal Substitution: moderate-to-large drop, agent clearly on different track
    if drop > 0.22 or subst_hits >= 2:
        return DriftType.GOAL_SUBST

    # Score drop + substitution keywords
    if drop > 0.15 and subst_hits >= 1:
        return DriftType.GOAL_SUBST

    # Default: Scope Creep (smallest deviation)
    return DriftType.SCOPE_CREEP


def severity_label(drift_type: DriftType, score: float) -> str:
    """
    Human-readable severity label for dashboard display.
    Returns: 'Low' / 'Medium' / 'High' / 'Critical'
    """
    if drift_type == DriftType.NONE:
        return "None"
    if drift_type == DriftType.CONTEXT_COLLAPSE:
        return "Critical"
    if drift_type == DriftType.GOAL_SUBST:
        return "High" if score < 0.50 else "Medium"
    # Scope Creep
    return "Low" if score > 0.60 else "Medium"


def correction_urgency(drift_type: DriftType, momentum: float) -> str:
    """
    Recommended correction urgency for the correction engine.
    Returns: 'soft' / 'medium' / 'hard' / 'abort'
    """
    if drift_type == DriftType.NONE:
        return "none"
    if drift_type == DriftType.CONTEXT_COLLAPSE:
        return "abort"
    if drift_type == DriftType.GOAL_SUBST:
        return "hard" if momentum < -0.05 else "medium"
    return "soft"  # scope creep


# ── self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  DriftWatch — Drift Classifier  (Day 2 / File 3)")
    print("=" * 55)

    test_cases = [
        (0.90, 0.68, +0.02, "Analyzing groundwater contamination near lithium sites", DriftType.NONE),
        (0.61, 0.68, -0.02, "Also exploring related aspects of battery recycling additionally", DriftType.SCOPE_CREEP),
        (0.44, 0.68, -0.05, "Actually switching to analyze EV market trends instead", DriftType.GOAL_SUBST),
        (0.29, 0.68, -0.09, "Completely different topic now, starting over from scratch", DriftType.CONTEXT_COLLAPSE),
    ]

    passed = 0
    for score, thresh, mom, text, expected in test_cases:
        result = classify_drift_type(score, thresh, mom, text)
        ok = result == expected
        if ok:
            passed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  score={score}  expected={expected.value:<20}  got={result.value}")
        if ok:
            sev = severity_label(result, score)
            urg = correction_urgency(result, mom)
            print(f"         severity={sev}  urgency={urg}")

    print(f"\n  {passed}/{len(test_cases)} tests passed")
