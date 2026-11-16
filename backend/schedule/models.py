"""
backend/schedule/models.py
--------------------------
Data structures and enums for campus zones, user roles, time windows,
and schedule evaluation contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    STUDENT    = "student"
    FACULTY    = "faculty"
    STAFF      = "staff"
    VISITOR    = "visitor"
    CONTRACTOR = "contractor"
    SECURITY   = "security"


class CampusZone(str, Enum):
    MAIN_GATE        = "main_gate"
    ENGINEERING_LAB  = "engineering_lab"
    LIBRARY          = "library"
    ADMIN_OFFICE     = "admin_office"
    DORMITORY        = "dormitory"
    SERVER_ROOM      = "server_room_high_security"


class DecisionOutcome(str, Enum):
    ALLOW                = "ALLOW"
    STEP_UP_VERIFICATION = "STEP-UP VERIFICATION"
    DENY                 = "DENY"


@dataclass
class TimeWindow:
    """Represents an active access schedule window in 24-hour time."""
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    days_of_week: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # 0=Mon, 6=Sun

    def is_active(self, weekday: int, hour: int, minute: int) -> bool:
        """Checks if current time falls within this operational window."""
        if weekday not in self.days_of_week:
            return False
        current_minutes = hour * 60 + minute
        window_start    = self.start_hour * 60 + self.start_minute
        window_end      = self.end_hour * 60 + self.end_minute
        return window_start <= current_minutes <= window_end

    def minutes_after_close(self, weekday: int, hour: int, minute: int) -> int:
        """Returns minutes elapsed since window closed (if closed today), else -1."""
        if weekday not in self.days_of_week:
            return -1
        current_minutes = hour * 60 + minute
        window_end      = self.end_hour * 60 + self.end_minute
        if current_minutes > window_end:
            return current_minutes - window_end
        return -1


@dataclass
class ZonePolicy:
    """Access policy definition for a specific campus facility."""
    zone: CampusZone
    name: str
    allowed_roles: list[UserRole]
    schedule_windows: list[TimeWindow]
    after_hours_grace_minutes: int = 60
    is_high_security: bool = False
    requires_step_up_always: bool = False


@dataclass
class EvaluationResult:
    """Consolidated outcome of the schedule + biometric policy fusion."""
    outcome: DecisionOutcome
    reason: str
    schedule_status: str
    zone: str
    role: str
    user_name: str
    timestamp_evaluated: str
    step_up_required: bool = False
    step_up_type: Optional[str] = None  # e.g., 'otp', 'active_challenge', 'supervisor_override'
