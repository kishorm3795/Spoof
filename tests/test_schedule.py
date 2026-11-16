"""
tests/test_schedule.py
----------------------
Unit and integration tests for Campus Access Schedule Engine:
Surprise Challenge 1: Access with Campus Schedule.
"""

from datetime import datetime
import sys
from pathlib import Path
import pytest

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from schedule.models import UserRole, CampusZone, DecisionOutcome
from schedule.engine import CampusScheduleEngine


@pytest.fixture
def engine():
    return CampusScheduleEngine()


def test_student_engineering_lab_normal_hours(engine):
    # Tuesday 14:30 (Weekday=1) -> Regular hours 08:00 - 20:00
    tuesday_afternoon = datetime(2026, 11, 17, 14, 30)
    outcome, reason, status = engine.evaluate_schedule(
        UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_afternoon
    )
    assert outcome == DecisionOutcome.ALLOW
    assert status == "within_schedule"


def test_student_engineering_lab_after_hours_grace(engine):
    # Tuesday 20:45 -> Lab closes at 20:00, 45 mins into grace period (max 120 mins)
    tuesday_evening = datetime(2026, 11, 17, 20, 45)
    outcome, reason, status = engine.evaluate_schedule(
        UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_evening
    )
    assert outcome == DecisionOutcome.STEP_UP_VERIFICATION
    assert status == "after_hours_grace"


def test_student_engineering_lab_curfew_denied(engine):
    # Tuesday 23:30 -> Past grace period
    tuesday_night = datetime(2026, 11, 17, 23, 30)
    outcome, reason, status = engine.evaluate_schedule(
        UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_night
    )
    assert outcome == DecisionOutcome.DENY
    assert status == "outside_schedule"


def test_student_server_room_unauthorized(engine):
    # Student attempting server room access at 12:00
    tuesday_noon = datetime(2026, 11, 17, 12, 0)
    outcome, reason, status = engine.evaluate_schedule(
        UserRole.STUDENT, CampusZone.SERVER_ROOM, tuesday_noon
    )
    assert outcome == DecisionOutcome.DENY
    assert status == "unauthorized_role"


def test_security_personnel_universal_clearance(engine):
    # 03:00 AM server room access by security guard
    night = datetime(2026, 11, 17, 3, 0)
    outcome, reason, status = engine.evaluate_schedule(
        UserRole.SECURITY, CampusZone.SERVER_ROOM, night
    )
    assert outcome == DecisionOutcome.ALLOW
    assert status == "security_clearance"


def test_biometric_fusion_truth_table(engine):
    tuesday_afternoon = datetime(2026, 11, 17, 14, 30)  # within schedule
    tuesday_evening   = datetime(2026, 11, 17, 20, 45)  # after-hours grace
    tuesday_night     = datetime(2026, 11, 17, 23, 30)  # closed

    # 1. ALLOW + ALLOW -> ALLOW
    res1 = engine.evaluate_access("ALLOW", "Alice", UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_afternoon)
    assert res1.outcome == DecisionOutcome.ALLOW
    assert not res1.step_up_required

    # 2. ALLOW + GRACE -> STEP-UP
    res2 = engine.evaluate_access("ALLOW", "Alice", UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_evening)
    assert res2.outcome == DecisionOutcome.STEP_UP_VERIFICATION
    assert res2.step_up_required

    # 3. ALLOW + CLOSED -> DENY
    res3 = engine.evaluate_access("ALLOW", "Alice", UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_night)
    assert res3.outcome == DecisionOutcome.DENY

    # 4. DENY + ANY SCHEDULE -> DENY (Biometric Veto)
    res4 = engine.evaluate_access("DENY", "Alice", UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_afternoon)
    assert res4.outcome == DecisionOutcome.DENY

    # 5. REQUEST_VERIFICATION + ALLOW -> STEP_UP
    res5 = engine.evaluate_access("REQUEST VERIFICATION", "Alice", UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_afternoon)
    assert res5.outcome == DecisionOutcome.STEP_UP_VERIFICATION
    assert res5.step_up_required


def test_emergency_lockdown(engine):
    tuesday_afternoon = datetime(2026, 11, 17, 14, 30)
    engine.set_lockdown(CampusZone.ENGINEERING_LAB, enabled=True, reason="Hazmat Spill")

    # Regular student denied during lockdown
    outcome, reason, status = engine.evaluate_schedule(
        UserRole.STUDENT, CampusZone.ENGINEERING_LAB, tuesday_afternoon
    )
    assert outcome == DecisionOutcome.DENY
    assert status == "emergency_lockdown"

    # Security still allowed for response
    sec_outcome, _, _ = engine.evaluate_schedule(
        UserRole.SECURITY, CampusZone.ENGINEERING_LAB, tuesday_afternoon
    )
    assert sec_outcome == DecisionOutcome.ALLOW


def test_campus_holiday(engine):
    holiday_date = datetime(2026, 12, 25, 10, 0)
    engine.add_holiday("2026-12-25")

    outcome, reason, status = engine.evaluate_schedule(
        UserRole.STUDENT, CampusZone.ENGINEERING_LAB, holiday_date
    )
    assert outcome == DecisionOutcome.DENY
    assert status == "campus_holiday_closed"
