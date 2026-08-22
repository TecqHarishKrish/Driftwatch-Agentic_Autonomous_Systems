def build_explanation(tier: int, drift_type: str) -> str:
    # Normalize CONTEXT_COLLAPSE to GOAL_COLLAPSE to match the messages dictionary
    if drift_type == "CONTEXT_COLLAPSE":
        drift_type = "GOAL_COLLAPSE"

    messages = {
        (1, "SCOPE_CREEP"):
            "The agent is slightly expanding beyond your task. "
            "DriftWatch is automatically nudging it back on track.",
        (1, "GOAL_SUBSTITUTION"):
            "The agent is beginning to replace your goal. "
            "DriftWatch is injecting a reminder of the original task.",
        (1, "GOAL_COLLAPSE"):
            "The agent is losing focus. "
            "DriftWatch is reinforcing the goal automatically.",
        (2, "SCOPE_CREEP"):
            "The agent has significantly drifted from your task. "
            "DriftWatch is re-injecting the full original goal now.",
        (2, "GOAL_SUBSTITUTION"):
            "The agent has replaced your goal with a different one. "
            "DriftWatch is forcing re-alignment with your original task.",
        (2, "GOAL_COLLAPSE"):
            "The agent has lost significant focus. "
            "DriftWatch is performing a full goal re-injection.",
        (3, "SCOPE_CREEP"):
            "CRITICAL: The agent is far outside your original task. "
            "DriftWatch recommends rolling back to the last stable step. "
            "Your approval is required to proceed.",
        (3, "GOAL_SUBSTITUTION"):
            "CRITICAL: The agent has fully replaced your goal. "
            "DriftWatch recommends a rollback to step 2. "
            "Your approval is required to proceed.",
        (3, "GOAL_COLLAPSE"):
            "CRITICAL: The agent has collapsed and lost all task context. "
            "DriftWatch recommends a rollback. "
            "Your approval is required to proceed.",
        (4, "GOAL_COLLAPSE"):
            "EMERGENCY: The agent has completely lost your task. "
            "DriftWatch recommends stopping execution entirely. "
            "Your approval is required to abort.",
        (4, "GOAL_SUBSTITUTION"):
            "EMERGENCY: Unrecoverable goal substitution detected. "
            "DriftWatch recommends aborting this run. "
            "Your approval is required.",
    }
    return messages.get(
        (tier, drift_type),
        f"Tier {tier} correction required for {drift_type}. "
        f"Your decision is needed."
    )

def get_severity_label(tier: int) -> str:
    return {1: "AUTO", 2: "AUTO", 3: "REVIEW", 4: "CRITICAL"}.get(
        tier, "UNKNOWN"
    )

def get_certificate_meaning(cert: str) -> str:
    return {
        "PASS": "Goal coherence verified. Output aligns with original task.",
        "WARN": "Minor drift detected. Output reviewed and corrected.",
        "FAIL": "Significant drift occurred. Manual review recommended."
    }.get(cert, "Certificate pending.")
