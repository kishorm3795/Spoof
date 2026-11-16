"""
backend/offline/local_evaluator.py
----------------------------------
Local safe decision processor and fail-secure policy executor.
Surprise Challenge 2 requirements:
1. "Continue using a safe local decision process."
2. "Avoid unsafe automatic access."

Fail-Secure Design:
- High-security facilities (e.g., Server Room) automatically lock down when offline.
- Stricter matching threshold (+15% tighter cosine distance margin required).
- Elevated liveness confidence required (0.78 vs 0.70 online).
- Borderline matches automatically divert to fallback step-up verification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from config import (
    THRESHOLD,
    OFFLINE_STRICTNESS_MULTIPLIER,
    LIVENESS_CONFIDENCE_THRESHOLD,
)
from schedule.models import CampusZone, DecisionOutcome, UserRole
from schedule.engine import CampusScheduleEngine
from .audit_log import OfflineAuditLog


class LocalSafeEvaluator:
    """
    Executes local biometric & schedule evaluation under air-gapped/offline conditions.
    Enforces fail-secure defaults to prevent unauthorized automatic access.
    """

    def __init__(
        self,
        audit_log: Optional[OfflineAuditLog] = None,
        schedule_engine: Optional[CampusScheduleEngine] = None,
    ):
        self.audit_log = audit_log or OfflineAuditLog()
        self.schedule_engine = schedule_engine or CampusScheduleEngine()

    def evaluate_offline(
        self,
        biometric_match: bool,
        user_name: str,
        user_role: UserRole | str,
        zone: CampusZone | str,
        cosine_distance: float,
        liveness_score: float,
        spoof_type: str = "genuine",
        dt: Optional[datetime] = None,
    ) -> dict:
        """
        Executes a safe offline access evaluation.

        Returns:
            dict containing:
                outcome (str): 'ALLOW', 'STEP-UP VERIFICATION', or 'DENY'
                reason (str): Detailed fail-secure rationale
                offline_mode (bool): True
                event_record (dict): Minimal audit record appended to disk
        """
        now = dt or datetime.now()
        zone_str = str(zone).split(".")[-1].lower()
        role_str = str(user_role).split(".")[-1].lower()

        # 1. Fail-Secure Rule: High-security zones lock down in offline mode
        if zone_str == CampusZone.SERVER_ROOM.value:
            record = self.audit_log.append_event(
                user_name=user_name,
                zone=zone_str,
                decision=DecisionOutcome.DENY.value,
                reason="Offline fail-secure: high-security facility locked down during network isolation",
                dt=now,
            )
            return {
                "outcome": DecisionOutcome.DENY.value,
                "reason": "High-security facility locks down during offline network isolation. Fail-secure denial.",
                "offline_mode": True,
                "event_id": record["event_id"],
                "step_up_required": False,
            }

        # 2. Check spoof / liveness with elevated offline threshold
        offline_live_threshold = min(0.95, LIVENESS_CONFIDENCE_THRESHOLD * 1.10)  # e.g., 0.77
        if liveness_score < 0.45 or spoof_type != "genuine":
            record = self.audit_log.append_event(
                user_name=user_name,
                zone=zone_str,
                decision=DecisionOutcome.DENY.value,
                reason=f"Offline anti-spoofing rejection: presentation attack detected ({spoof_type})",
                dt=now,
            )
            return {
                "outcome": DecisionOutcome.DENY.value,
                "reason": f"Presentation attack detected ({spoof_type}). Fail-secure denial.",
                "offline_mode": True,
                "event_id": record["event_id"],
                "step_up_required": False,
            }

        # 3. Evaluate Identity with strict offline threshold
        strict_threshold = THRESHOLD / OFFLINE_STRICTNESS_MULTIPLIER  # ~0.304 instead of 0.35
        if not biometric_match or cosine_distance > THRESHOLD:
            record = self.audit_log.append_event(
                user_name=user_name,
                zone=zone_str,
                decision=DecisionOutcome.DENY.value,
                reason="Offline identity mismatch: biometric distance exceeds acceptable threshold",
                dt=now,
            )
            return {
                "outcome": DecisionOutcome.DENY.value,
                "reason": "Biometric identity could not be verified from local cache.",
                "offline_mode": True,
                "event_id": record["event_id"],
                "step_up_required": False,
            }

        # If match is in borderline range [strict_threshold, THRESHOLD] or liveness is borderline
        needs_step_up = (
            cosine_distance > strict_threshold
            or liveness_score < offline_live_threshold
        )

        # 4. Evaluate Campus Schedule using local policy engine
        sched_outcome, sched_reason, _ = self.schedule_engine.evaluate_schedule(
            role=role_str,
            zone=zone_str,
            dt=now,
        )

        if sched_outcome == DecisionOutcome.DENY:
            record = self.audit_log.append_event(
                user_name=user_name,
                zone=zone_str,
                decision=DecisionOutcome.DENY.value,
                reason=f"Offline schedule denial: {sched_reason}",
                dt=now,
            )
            return {
                "outcome": DecisionOutcome.DENY.value,
                "reason": f"Access denied: {sched_reason}",
                "offline_mode": True,
                "event_id": record["event_id"],
                "step_up_required": False,
            }

        # If schedule requires step-up or biometric confidence is borderline
        if sched_outcome == DecisionOutcome.STEP_UP_VERIFICATION or needs_step_up:
            record = self.audit_log.append_event(
                user_name=user_name,
                zone=zone_str,
                decision=DecisionOutcome.STEP_UP_VERIFICATION.value,
                reason="Offline step-up required: stricter offline threshold or schedule grace period",
                dt=now,
            )
            return {
                "outcome": DecisionOutcome.STEP_UP_VERIFICATION.value,
                "reason": "Offline step-up verification required (fallback emergency passkey or OTP).",
                "offline_mode": True,
                "event_id": record["event_id"],
                "step_up_required": True,
                "step_up_type": "offline_emergency_totp",
            }

        # 5. Full clearance: Verified live, strict identity match, authorized schedule
        record = self.audit_log.append_event(
            user_name=user_name,
            zone=zone_str,
            decision=DecisionOutcome.ALLOW.value,
            reason="Offline access authorized: strict biometric criteria and local schedule verified",
            dt=now,
        )
        return {
            "outcome": DecisionOutcome.ALLOW.value,
            "reason": "Offline access authorized: identity and local schedule verified.",
            "offline_mode": True,
            "event_id": record["event_id"],
            "step_up_required": False,
        }
