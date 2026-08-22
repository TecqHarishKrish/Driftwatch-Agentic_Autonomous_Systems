import threading
import time

_pending_decisions = {}
_decision_events   = {}

def request_user_decision(session_id: str, correction_payload: dict,
                           timeout: int = 120) -> str:
    """
    Blocks the calling thread until user sends a decision
    via POST /api/decision/<session_id> or timeout expires.
    Returns: "approve" or "reject"
    """
    _pending_decisions[session_id] = {
        **correction_payload,
        "user_decision": None
    }
    event = threading.Event()
    _decision_events[session_id] = event

    event.wait(timeout=timeout)

    decision = _pending_decisions.pop(session_id, {})
    _decision_events.pop(session_id, None)
    return decision.get("user_decision") or "approve"

def resolve_decision(session_id: str, decision: str) -> bool:
    """
    Called by the Flask route when user clicks Approve/Reject.
    Unblocks the waiting execution thread.
    Returns True if a pending decision existed, False otherwise.
    """
    if session_id not in _pending_decisions:
        return False
    _pending_decisions[session_id]["user_decision"] = decision
    if session_id in _decision_events:
        _decision_events[session_id].set()
    return True

def has_pending_decision(session_id: str) -> bool:
    return session_id in _pending_decisions

def get_pending_payload(session_id: str) -> dict:
    return _pending_decisions.get(session_id, {})
