"""
tests/test_schedule.py
----------------------
Unit and integration tests for Campus Access Schedule Engine:
Surprise Challenge 1: Access with Campus Schedule.
"""

from datetime import datetime
import sys
from pathlib import Path
import sys

# Light fixture helper compatible with pytest and standalone test runner
try:
    if "pytest" in sys.modules:
        import pytest
        fixture = pytest.fixture
    else:
        def fixture(f):
            return f
except Exception:
    def fixture(f):
        return f

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from schedule.models import UserRole, CampusZone, DecisionOutcome
from schedule.engine import CampusScheduleEngine


@fixture
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


def test_admin_universal_clearance(engine):
    # Admin can access high-security server room at any hour
    midnight = datetime(2026, 11, 17, 2, 30)
    outcome, reason, status = engine.evaluate_schedule(
        UserRole.ADMIN, CampusZone.SERVER_ROOM, midnight
    )
    assert outcome == DecisionOutcome.ALLOW
    assert status == "admin_clearance"

    # Admin has universal executive clearance across all campus zones
    all_zones = [
        CampusZone.MAIN_GATE,
        CampusZone.ENGINEERING_LAB,
        CampusZone.LIBRARY,
        CampusZone.ADMIN_OFFICE,
        CampusZone.DORMITORY,
        CampusZone.SERVER_ROOM,
        CampusZone.FACULTY_LOUNGE,
        CampusZone.CLASSROOM_HALL,
    ]
    for z in all_zones:
        out, _, st = engine.evaluate_schedule(UserRole.ADMIN, z, midnight)
        assert out == DecisionOutcome.ALLOW
        assert st == "admin_clearance"


def test_admin_lockdown_override(engine):
    tuesday_noon = datetime(2026, 11, 17, 12, 0)
    engine.set_lockdown(CampusZone.ENGINEERING_LAB, enabled=True, reason="Chemical Containment")

    # Regular student and user denied
    out_student, _, _ = engine.evaluate_schedule("student", "engineering_lab", tuesday_noon)
    assert out_student == DecisionOutcome.DENY

    # Admin and Security can access
    out_admin, _, _ = engine.evaluate_schedule("admin", "engineering_lab", tuesday_noon)
    assert out_admin == DecisionOutcome.ALLOW

    out_sec, _, _ = engine.evaluate_schedule("security", "engineering_lab", tuesday_noon)
    assert out_sec == DecisionOutcome.ALLOW


def test_teacher_faculty_lounge_and_lab_extended(engine):
    # Teacher can access Faculty Lounge during standard operating hours
    afternoon = datetime(2026, 11, 17, 15, 0)
    out_teacher, _, status = engine.evaluate_schedule(
        UserRole.TEACHER, CampusZone.FACULTY_LOUNGE, afternoon
    )
    assert out_teacher == DecisionOutcome.ALLOW
    assert status == "within_schedule"

    # Teacher can access Classrooms during academic hours
    out_class, _, status_class = engine.evaluate_schedule(
        UserRole.TEACHER, CampusZone.CLASSROOM_HALL, afternoon
    )
    assert out_class == DecisionOutcome.ALLOW

    # Students cannot access Faculty Lounge
    out_student, _, _ = engine.evaluate_schedule(
        UserRole.STUDENT, CampusZone.FACULTY_LOUNGE, afternoon
    )
    assert out_student == DecisionOutcome.DENY

    # Teachers have extended 24/7 research privileges in engineering lab (past student curfew)
    late_night = datetime(2026, 11, 17, 23, 45)
    out_lab, _, status_lab = engine.evaluate_schedule(
        UserRole.TEACHER, CampusZone.ENGINEERING_LAB, late_night
    )
    assert out_lab == DecisionOutcome.ALLOW
    assert status_lab == "faculty_research_clearance"

    # Teacher denied from student dormitories and server room
    out_dorm, _, _ = engine.evaluate_schedule(UserRole.TEACHER, CampusZone.DORMITORY, afternoon)
    assert out_dorm == DecisionOutcome.DENY

    out_server, _, _ = engine.evaluate_schedule(UserRole.TEACHER, CampusZone.SERVER_ROOM, afternoon)
    assert out_server == DecisionOutcome.DENY


def test_student_all_persona_clearances(engine):
    daytime = datetime(2026, 11, 17, 14, 0)
    night = datetime(2026, 11, 17, 23, 30)

    # 1. Dormitory: 24/7 allowed
    out_dorm, _, _ = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.DORMITORY, night)
    assert out_dorm == DecisionOutcome.ALLOW

    # 2. Classroom Hall: allowed in daytime
    out_class, _, _ = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.CLASSROOM_HALL, daytime)
    assert out_class == DecisionOutcome.ALLOW

    # 3. Library: allowed in daytime
    out_lib, _, _ = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.LIBRARY, daytime)
    assert out_lib == DecisionOutcome.ALLOW

    # 4. Engineering Lab: allowed in daytime, grace step-up at night, denied past curfew
    out_lab_day, _, _ = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.ENGINEERING_LAB, daytime)
    assert out_lab_day == DecisionOutcome.ALLOW

    grace_time = datetime(2026, 11, 17, 20, 45)
    out_lab_grace, _, st_grace = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.ENGINEERING_LAB, grace_time)
    assert out_lab_grace == DecisionOutcome.STEP_UP_VERIFICATION
    assert st_grace == "after_hours_grace"

    out_lab_curfew, _, _ = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.ENGINEERING_LAB, night)
    assert out_lab_curfew == DecisionOutcome.DENY

    # 5. Unauthorized zones: faculty lounge, admin office, server room
    out_lounge, _, _ = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.FACULTY_LOUNGE, daytime)
    assert out_lounge == DecisionOutcome.DENY

    out_admin_off, _, _ = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.ADMIN_OFFICE, daytime)
    assert out_admin_off == DecisionOutcome.DENY

    out_server, _, _ = engine.evaluate_schedule(UserRole.STUDENT, CampusZone.SERVER_ROOM, daytime)
    assert out_server == DecisionOutcome.DENY


def test_user_general_access_rules(engine):
    afternoon = datetime(2026, 11, 17, 14, 0)
    # General campus user can access Main Gate and Library
    out_gate, _, _ = engine.evaluate_schedule(UserRole.USER, CampusZone.MAIN_GATE, afternoon)
    assert out_gate == DecisionOutcome.ALLOW

    out_lib, _, _ = engine.evaluate_schedule("user", "library", afternoon)
    assert out_lib == DecisionOutcome.ALLOW

    # General campus user is denied from classroom hall, faculty lounge, server room, and admin office
    out_class, _, _ = engine.evaluate_schedule(UserRole.USER, CampusZone.CLASSROOM_HALL, afternoon)
    assert out_class == DecisionOutcome.DENY

    out_lounge, _, _ = engine.evaluate_schedule(UserRole.USER, CampusZone.FACULTY_LOUNGE, afternoon)
    assert out_lounge == DecisionOutcome.DENY

    out_server, _, _ = engine.evaluate_schedule(UserRole.USER, CampusZone.SERVER_ROOM, afternoon)
    assert out_server == DecisionOutcome.DENY

    out_office, _, _ = engine.evaluate_schedule("user", "admin_office", afternoon)
    assert out_office == DecisionOutcome.DENY

    out_lab, _, _ = engine.evaluate_schedule("user", "engineering_lab", afternoon)
    assert out_lab == DecisionOutcome.DENY
