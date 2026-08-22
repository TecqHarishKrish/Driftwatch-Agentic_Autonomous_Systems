from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
import json, uuid, time, os

class SessionPhase(Enum):
    ONBOARDING = "onboarding"
    EXECUTING  = "executing"
    REVIEWING  = "reviewing"
    COMPLETE   = "complete"

class CorrectionStatus(Enum):
    AUTO_APPLIED  = "auto_applied"
    PENDING_USER  = "pending_user"
    USER_APPROVED = "user_approved"
    USER_REJECTED = "user_rejected"

@dataclass
class StepRecord:
    step_number: int
    action: str
    drift_score: float
    momentum: float
    drift_type: Optional[str]
    timestamp: float = field(default_factory=time.time)

@dataclass
class CorrectionEvent:
    step_number: int
    tier: int
    drift_type: str
    correction_applied: str
    status: CorrectionStatus
    user_decision: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

@dataclass
class WorkflowSession:
    session_id: str = field(
        default_factory=lambda: str(uuid.uuid4())[:8]
    )
    task: str = ""
    sensitivity: float = 0.75
    goal_anchors: List[str] = field(default_factory=list)
    phase: SessionPhase = SessionPhase.ONBOARDING
    steps: List[StepRecord] = field(default_factory=list)
    drift_events: List[CorrectionEvent] = field(default_factory=list)
    raw_output: str = ""
    corrected_output: str = ""
    coherence_certificate: str = "pending"
    final_score: float = 0.0
    user_decisions: List[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    error_message: Optional[str] = None

    def to_dict(self):
        import dataclasses
        d = dataclasses.asdict(self)
        d['phase'] = self.phase.value \
            if isinstance(self.phase, SessionPhase) else self.phase
        for ev in d.get('drift_events', []):
            if isinstance(ev.get('status'), CorrectionStatus):
                ev['status'] = ev['status'].value
        return d

    def save(self, path="sessions"):
        save_session_dict(self.session_id, self.to_dict(), path)

    @classmethod
    def load(cls, session_id, path="sessions"):
        fpath = f"{path}/{session_id}.json"
        if not os.path.exists(fpath):
            raise FileNotFoundError(
                f"Session {session_id} not found"
            )
        with open(fpath) as f:
            return json.load(f)

def save_session_dict(session_id, ws_data, path="sessions"):
    os.makedirs(path, exist_ok=True)
    temp_path = f"{path}/{session_id}.json.tmp"
    with open(temp_path, "w") as f:
        json.dump(ws_data, f, indent=2)
    os.replace(temp_path, f"{path}/{session_id}.json")
