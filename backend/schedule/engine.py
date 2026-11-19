"""
backend/schedule/engine.py
--------------------------
Campus Access Schedule Engine.
Combines biometric liveness and identity results with temporal facility policies:
  BIOMETRIC RESULT + CAMPUS ACCESS SCHEDULE -> ALLOW / STEP-UP VERIFICATION / DENY
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .models import (
    UserRole,
    CampusZone,
    DecisionOutcome,
    TimeWindow,
    ZonePolicy,
    EvaluationResult,
)


class CampusScheduleEngine:
    """
    Evaluates campus access schedule rules and combines them with biometric signals.
    """

    def __init__(self):
        self.policies: dict[CampusZone, ZonePolicy] = self._init_default_policies()
        self.holidays: set[str] = set()  # format: 'YYYY-MM-DD'
        self.active_lockdowns: dict[CampusZone, str] = {}  # zone -> reason

    def add_holiday(self, date_str: str) -> None:
        """Registers a campus holiday in 'YYYY-MM-DD' format."""
        self.holidays.add(date_str)

    def set_lockdown(self, zone: CampusZone | str, enabled: bool = True, reason: str = "Emergency curfew") -> None:
        """Enforces or releases an emergency perimeter lockdown for a facility."""
        zone_enum = zone if isinstance(zone, CampusZone) else CampusZone(str(zone).split(".")[-1].lower())
        if enabled:
            self.active_lockdowns[zone_enum] = reason
        else:
            self.active_lockdowns.pop(zone_enum, None)

    def is_lockdown_active(self, zone: CampusZone | str) -> tuple[bool, Optional[str]]:
        """Checks if an emergency facility lockdown is active."""
        zone_enum = zone if isinstance(zone, CampusZone) else CampusZone(str(zone).split(".")[-1].lower())
        if zone_enum in self.active_lockdowns:
            return True, self.active_lockdowns[zone_enum]
        return False, None

    def _init_default_policies(self) -> dict[CampusZone, ZonePolicy]:
        """Configures operational access windows across campus facilities."""
        weekday_days = [0, 1, 2, 3, 4]        # Mon-Fri
        weekend_days = [5, 6]                 # Sat-Sun
        all_days     = [0, 1, 2, 3, 4, 5, 6]  # All week

        return {
            # 1. Main Gate: Primary perimeter access point
            CampusZone.MAIN_GATE: ZonePolicy(
                zone=CampusZone.MAIN_GATE,
                name="Campus Main Entrance",
                allowed_roles=[
                    UserRole.ADMIN,
                    UserRole.DEAN,
                    UserRole.TEACHER,
                    UserRole.FACULTY,
                    UserRole.STUDENT,
                    UserRole.USER,
                    UserRole.RESEARCHER,
                    UserRole.STAFF,
                    UserRole.SECURITY,
                    UserRole.VISITOR,
                    UserRole.CONTRACTOR,
                    UserRole.MAINTENANCE,
                ],
                schedule_windows=[
                    # 24/7 for regular campus members
                    TimeWindow(0, 0, 23, 59, all_days),
                ],
                after_hours_grace_minutes=60,
                is_high_security=False,
            ),

            # 2. Engineering Lab: Specialized equipment requiring curfew enforcement
            CampusZone.ENGINEERING_LAB: ZonePolicy(
                zone=CampusZone.ENGINEERING_LAB,
                name="Engineering Research & Computer Lab",
                allowed_roles=[
                    UserRole.ADMIN,
                    UserRole.DEAN,
                    UserRole.TEACHER,
                    UserRole.FACULTY,
                    UserRole.RESEARCHER,
                    UserRole.STUDENT,
                    UserRole.STAFF,
                    UserRole.SECURITY,
                    UserRole.MAINTENANCE,
                ],
                schedule_windows=[
                    # Mon-Sat 08:00 to 20:00 regular access for students
                    TimeWindow(8, 0, 20, 0, [0, 1, 2, 3, 4, 5]),
                ],
                after_hours_grace_minutes=120,  # 20:00 to 22:00 allowed with step-up verification
                is_high_security=False,
            ),

            # 3. Library: Study spaces with extended student hours
            CampusZone.LIBRARY: ZonePolicy(
                zone=CampusZone.LIBRARY,
                name="Central Academic Library",
                allowed_roles=[
                    UserRole.ADMIN,
                    UserRole.DEAN,
                    UserRole.TEACHER,
                    UserRole.FACULTY,
                    UserRole.RESEARCHER,
                    UserRole.STUDENT,
                    UserRole.USER,
                    UserRole.STAFF,
                    UserRole.SECURITY,
                    UserRole.VISITOR,
                ],
                schedule_windows=[
                    # 07:00 to 23:00 everyday
                    TimeWindow(7, 0, 23, 0, all_days),
                ],
                after_hours_grace_minutes=30,
                is_high_security=False,
            ),

            # 4. Admin Office: Business hours only
            CampusZone.ADMIN_OFFICE: ZonePolicy(
                zone=CampusZone.ADMIN_OFFICE,
                name="Administrative & Registrar Offices",
                allowed_roles=[
                    UserRole.ADMIN,
                    UserRole.DEAN,
                    UserRole.STAFF,
                    UserRole.TEACHER,
                    UserRole.FACULTY,
                    UserRole.SECURITY,
                ],
                schedule_windows=[
                    # Mon-Fri 08:30 to 17:30
                    TimeWindow(8, 30, 17, 30, weekday_days),
                ],
                after_hours_grace_minutes=45,
                is_high_security=False,
            ),

            # 5. Dormitory: Residence building
            CampusZone.DORMITORY: ZonePolicy(
                zone=CampusZone.DORMITORY,
                name="Student Residential Dormitories",
                allowed_roles=[
                    UserRole.STUDENT,
                    UserRole.ADMIN,
                    UserRole.SECURITY,
                    UserRole.MAINTENANCE,
                ],
                schedule_windows=[
                    TimeWindow(0, 0, 23, 59, all_days),
                ],
                after_hours_grace_minutes=0,
                is_high_security=False,
            ),

            # 6. Server Room: Critical infrastructure
            CampusZone.SERVER_ROOM: ZonePolicy(
                zone=CampusZone.SERVER_ROOM,
                name="High-Security Datacenter & Server Room",
                allowed_roles=[
                    UserRole.ADMIN,
                    UserRole.STAFF,
                    UserRole.SECURITY,
                    UserRole.MAINTENANCE,
                ],
                schedule_windows=[
                    # Standard maintenance hours: Mon-Fri 09:00 to 17:00
                    TimeWindow(9, 0, 17, 0, weekday_days),
                ],
                after_hours_grace_minutes=60,
                is_high_security=True,
                requires_step_up_always=False,  # Regular hours standard match; off-hours step-up
            ),

            # 7. Faculty Lounge: Academic staff relaxation and meeting space
            CampusZone.FACULTY_LOUNGE: ZonePolicy(
                zone=CampusZone.FACULTY_LOUNGE,
                name="Faculty & Department Lounge",
                allowed_roles=[
                    UserRole.TEACHER,
                    UserRole.FACULTY,
                    UserRole.DEAN,
                    UserRole.ADMIN,
                    UserRole.STAFF,
                    UserRole.SECURITY,
                    UserRole.MAINTENANCE,
                ],
                schedule_windows=[
                    TimeWindow(6, 0, 23, 0, all_days),
                ],
                after_hours_grace_minutes=60,
                is_high_security=False,
            ),

            # 8. Classroom Hall: Lecture halls & standard teaching rooms
            CampusZone.CLASSROOM_HALL: ZonePolicy(
                zone=CampusZone.CLASSROOM_HALL,
                name="Lecture Halls & Academic Classrooms",
                allowed_roles=[
                    UserRole.TEACHER,
                    UserRole.FACULTY,
                    UserRole.DEAN,
                    UserRole.ADMIN,
                    UserRole.STUDENT,
                    UserRole.STAFF,
                    UserRole.SECURITY,
                    UserRole.MAINTENANCE,
                ],
                schedule_windows=[
                    TimeWindow(7, 30, 21, 30, [0, 1, 2, 3, 4, 5]),
                ],
                after_hours_grace_minutes=45,
                is_high_security=False,
            ),
        }

    def evaluate_schedule(
        self,
        role: UserRole | str,
        zone: CampusZone | str,
        dt: Optional[datetime] = None,
    ) -> tuple[DecisionOutcome, str, str]:
        """
        Evaluates purely the temporal and role-based permissions.

        Returns:
            (DecisionOutcome, reason_message, schedule_status)
        """
        if isinstance(role, UserRole):
            role_enum = role
        else:
            role_str = str(role).split(".")[-1].lower()
            role_enum = UserRole(role_str)

        if isinstance(zone, CampusZone):
            zone_enum = zone
        else:
            zone_clean = str(zone).split(".")[-1].lower()
            if zone_clean in ["server_room", "server_room_high_security"]:
                zone_enum = CampusZone.SERVER_ROOM
            else:
                zone_enum = CampusZone(zone_clean)

        if zone_enum not in self.policies:
            return DecisionOutcome.DENY, f"Unknown campus zone: {zone}", "unknown_zone"

        policy = self.policies[zone_enum]

        now = dt or datetime.now()
        date_key = now.strftime("%Y-%m-%d")

        # Emergency Lockdown Check
        is_locked, lock_reason = self.is_lockdown_active(zone_enum)
        if is_locked and role_enum != UserRole.SECURITY:
            return (
                DecisionOutcome.DENY,
                f"Facility {policy.name} is under emergency lockdown: {lock_reason}",
                "emergency_lockdown",
            )

        # Campus Holiday Check (academic facilities closed except security)
        if date_key in self.holidays and zone_enum not in [CampusZone.MAIN_GATE, CampusZone.DORMITORY]:
            if role_enum not in [UserRole.SECURITY, UserRole.STAFF]:
                return (
                    DecisionOutcome.DENY,
                    f"Campus holiday observed ({date_key}). Academic access suspended.",
                    "campus_holiday_closed",
                )

# Universal Clearance Privileges:
        # 1. Security personnel always have bypass privileges across standard campus facilities
        if role_enum == UserRole.SECURITY:
            return DecisionOutcome.ALLOW, "Security personnel authorized across all facilities", "security_clearance"

        # 2. Campus Administrators have universal administrative override across all facilities
        if role_enum == UserRole.ADMIN:
            return DecisionOutcome.ALLOW, "Campus Administrator authorized with universal executive clearance", "admin_clearance"

        # 3. Academic Deans have senior administrative clearance
        if role_enum == UserRole.DEAN and zone_enum != CampusZone.SERVER_ROOM:
            return DecisionOutcome.ALLOW, "Academic Dean authorized with senior administrative clearance", "dean_clearance"


        # Check role permission
        if role_enum not in policy.allowed_roles:
            return (
                DecisionOutcome.DENY,
                f"Role '{role_enum.value}' is not authorized to access {policy.name}",
                "unauthorized_role",
            )

        now = dt or datetime.now()
        weekday = now.weekday()
        hour = now.hour
        minute = now.minute

        # Check if inside any active schedule window
        for window in policy.schedule_windows:
            if window.is_active(weekday, hour, minute):
                # High security zones during normal hours may still enforce step-up if policy specifies
                if policy.is_high_security and policy.requires_step_up_always:
                    return (
                        DecisionOutcome.STEP_UP_VERIFICATION,
                        f"High-security facility {policy.name} requires dual-factor step-up verification",
                        "high_security_step_up",
                    )
                return (
                    DecisionOutcome.ALLOW,
                    f"Authorized schedule: within permitted operating hours for {policy.name}",
                    "within_schedule",
                )

        # Check if within after-hours grace period (step-up verification)
        if policy.after_hours_grace_minutes > 0:
            for window in policy.schedule_windows:
                mins_after = window.minutes_after_close(weekday, hour, minute)
                if 0 <= mins_after <= policy.after_hours_grace_minutes:
                    return (
                        DecisionOutcome.STEP_UP_VERIFICATION,
                        f"After-hours access ({mins_after}m post-close) requires step-up verification code",
                        "after_hours_grace",
                    )

        # Otherwise completely closed / curfew denied
        return (
            DecisionOutcome.DENY,
            f"Facility {policy.name} is currently closed to {role_enum.value}s at {now.strftime('%H:%M')}",
            "outside_schedule",
        )

    def evaluate_access(
        self,
        biometric_outcome: str,
        user_name: str,
        user_role: UserRole | str,
        zone: CampusZone | str,
        dt: Optional[datetime] = None,
    ) -> EvaluationResult:
        """
        Fuses Biometric Result + Campus Access Schedule:
            BIOMETRIC RESULT + CAMPUS ACCESS SCHEDULE -> ALLOW / STEP-UP VERIFICATION / DENY
        """
        now = dt or datetime.now()
        timestamp_str = now.isoformat()

        sched_outcome, sched_reason, sched_status = self.evaluate_schedule(user_role, zone, now)

        bio_clean = biometric_outcome.strip().upper()

        # Fusion Truth Table:
        # 1. If biometric is DENY -> Result is DENY regardless of schedule
        if bio_clean == "DENY":
            return EvaluationResult(
                outcome=DecisionOutcome.DENY,
                reason="Biometric verification failed: presentation attack detected or identity mismatch",
                schedule_status=sched_status,
                zone=str(zone),
                role=str(user_role),
                user_name=user_name,
                timestamp_evaluated=timestamp_str,
                step_up_required=False,
            )

        # 2. If biometric is REQUEST VERIFICATION
        if bio_clean in ["REQUEST VERIFICATION", "REQUEST_VERIFICATION", "STEP_UP_VERIFICATION", "STEP-UP VERIFICATION"]:
            if sched_outcome == DecisionOutcome.DENY:
                return EvaluationResult(
                    outcome=DecisionOutcome.DENY,
                    reason=f"Access denied: {sched_reason} (and biometric confidence borderline)",
                    schedule_status=sched_status,
                    zone=str(zone),
                    role=str(user_role),
                    user_name=user_name,
                    timestamp_evaluated=timestamp_str,
                    step_up_required=False,
                )
            else:
                return EvaluationResult(
                    outcome=DecisionOutcome.STEP_UP_VERIFICATION,
                    reason="Borderline biometric confidence: step-up OTP or active action challenge required",
                    schedule_status=sched_status,
                    zone=str(zone),
                    role=str(user_role),
                    user_name=user_name,
                    timestamp_evaluated=timestamp_str,
                    step_up_required=True,
                    step_up_type="biometric_fallback",
                )

        # 3. If biometric is ALLOW
        if bio_clean == "ALLOW":
            if sched_outcome == DecisionOutcome.ALLOW:
                return EvaluationResult(
                    outcome=DecisionOutcome.ALLOW,
                    reason="Access granted: biometric authentication verified and authorized within campus schedule",
                    schedule_status=sched_status,
                    zone=str(zone),
                    role=str(user_role),
                    user_name=user_name,
                    timestamp_evaluated=timestamp_str,
                    step_up_required=False,
                )
            elif sched_outcome == DecisionOutcome.STEP_UP_VERIFICATION:
                return EvaluationResult(
                    outcome=DecisionOutcome.STEP_UP_VERIFICATION,
                    reason=f"Step-up authorization required: {sched_reason}",
                    schedule_status=sched_status,
                    zone=str(zone),
                    role=str(user_role),
                    user_name=user_name,
                    timestamp_evaluated=timestamp_str,
                    step_up_required=True,
                    step_up_type="schedule_after_hours_otp",
                )
            else:  # sched_outcome == DecisionOutcome.DENY
                return EvaluationResult(
                    outcome=DecisionOutcome.DENY,
                    reason=f"Access denied by campus schedule: {sched_reason}",
                    schedule_status=sched_status,
                    zone=str(zone),
                    role=str(user_role),
                    user_name=user_name,
                    timestamp_evaluated=timestamp_str,
                    step_up_required=False,
                )

        # Unknown fallback: fail-secure DENY
        return EvaluationResult(
            outcome=DecisionOutcome.DENY,
            reason="Unrecognized biometric status. Fail-secure denial.",
            schedule_status=sched_status,
            zone=str(zone),
            role=str(user_role),
            user_name=user_name,
            timestamp_evaluated=timestamp_str,
            step_up_required=False,
        )
