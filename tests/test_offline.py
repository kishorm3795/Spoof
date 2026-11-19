"""
tests/test_offline.py
---------------------
Unit and integration tests for Offline Mode and Safe Access:
Surprise Challenge 2:
1. Safe local decision process.
2. Avoid unsafe automatic access (fail-secure).
3. Fallback verification (TOTP / emergency PIN).
4. Minimum temporary information storage (hash chain integrity & privacy).
5. Synchronization when connection returns.
"""

import sys
import json
import time
from datetime import datetime
from pathlib import Path
import pytest

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from offline.audit_log import OfflineAuditLog
from offline.local_evaluator import LocalSafeEvaluator
from offline.totp_fallback import TOTPFallback
from offline.sync_manager import SyncManager
from schedule.models import CampusZone, DecisionOutcome, UserRole


@pytest.fixture
def temp_audit_log(tmp_path):
    log_file = tmp_path / "test_offline_audit.jsonl"
    return OfflineAuditLog(log_path=log_file)


def test_audit_log_chain_and_privacy(temp_audit_log):
    # Append events
    e1 = temp_audit_log.append_event("Alice", "main_gate", "ALLOW", "Biometric verified")
    e2 = temp_audit_log.append_event("Bob", "engineering_lab", "DENY", "Presentation attack detected")
    e3 = temp_audit_log.append_event("Charlie", "library", "STEP-UP VERIFICATION", "Grace period OTP")

    # 1. Verify privacy: No raw names or biometrics in payload
    assert "face" not in e1
    assert "image" not in e1
    assert "vector" not in e1
    assert e1["pseudonym_hash"] != "Alice"

    # 2. Verify hash chain integrity
    is_valid, msg = temp_audit_log.verify_chain_integrity()
    assert is_valid is True
    assert "3 events" in msg


def test_audit_log_tamper_detection(temp_audit_log):
    temp_audit_log.append_event("Alice", "main_gate", "ALLOW", "Verified")
    temp_audit_log.append_event("Bob", "engineering_lab", "DENY", "Spoof")

    # Tamper with the file on disk (simulate adversary changing DENY to ALLOW)
    lines = []
    with open(temp_audit_log.log_path, "r") as f:
        for line in f:
            record = json.loads(line)
            if record["decision"] == "DENY":
                record["decision"] = "ALLOW"
            lines.append(json.dumps(record))

    with open(temp_audit_log.log_path, "w") as f:
        for l in lines:
            f.write(l + "\n")

    # Verify that tamper-detection immediately flags the forgery
    is_valid, msg = temp_audit_log.verify_chain_integrity()
    assert is_valid is False
    assert "Hash mismatch" in msg or "Signature forgery" in msg


def test_local_evaluator_fail_secure(temp_audit_log):
    evaluator = LocalSafeEvaluator(audit_log=temp_audit_log)
    tuesday_afternoon = datetime(2026, 11, 17, 14, 0)

    # 1. High security server room locks down in offline mode -> DENY
    res_server = evaluator.evaluate_offline(
        biometric_match=True,
        user_name="Alice",
        user_role=UserRole.STAFF,
        zone=CampusZone.SERVER_ROOM,
        cosine_distance=0.15,
        liveness_score=0.90,
        dt=tuesday_afternoon,
    )
    assert res_server["outcome"] == DecisionOutcome.DENY.value
    assert "fail-secure" in res_server["reason"].lower()

    # 2. Strict threshold: Marginal match (0.33 > 0.304 strict threshold) -> STEP-UP
    res_marginal = evaluator.evaluate_offline(
        biometric_match=True,
        user_name="Alice",
        user_role=UserRole.STUDENT,
        zone=CampusZone.ENGINEERING_LAB,
        cosine_distance=0.33,  # Within 0.35 online, but fails strict offline
        liveness_score=0.90,
        dt=tuesday_afternoon,
    )
    assert res_marginal["outcome"] == DecisionOutcome.STEP_UP_VERIFICATION.value
    assert res_marginal["step_up_required"] is True

    # 3. Spoof detected -> Strict DENY
    res_spoof = evaluator.evaluate_offline(
        biometric_match=True,
        user_name="Alice",
        user_role=UserRole.STUDENT,
        zone=CampusZone.ENGINEERING_LAB,
        cosine_distance=0.15,
        liveness_score=0.30,
        spoof_type="printed_photo",
        dt=tuesday_afternoon,
    )
    assert res_spoof["outcome"] == DecisionOutcome.DENY.value

    # 4. Genuine match within schedule -> ALLOW
    res_allow = evaluator.evaluate_offline(
        biometric_match=True,
        user_name="Alice",
        user_role=UserRole.STUDENT,
        zone=CampusZone.ENGINEERING_LAB,
        cosine_distance=0.20,
        liveness_score=0.90,
        dt=tuesday_afternoon,
    )
    assert res_allow["outcome"] == DecisionOutcome.ALLOW.value


def test_totp_emergency_fallback():
    totp = TOTPFallback(base32_secret="JBSWY3DPEHPK3PXP")
    now_epoch = time.time()

    token = totp.generate_token(now_epoch)
    assert len(token) == 6
    assert token.isdigit()

    # Successful verification
    assert totp.verify_token(token, for_time=now_epoch) is True

    # Replay attack prevention: Same token used again in same window rejected
    assert totp.verify_token(token, for_time=now_epoch) is False

    # Master security override pin
    valid, reason = totp.verify_fallback(TOTPFallback.MASTER_OVERRIDE_PIN, "Admin", "main_gate")
    assert valid is True
    assert "master security override" in reason.lower()


def test_sync_reconciliation_flow(tmp_path):
    audit_file = tmp_path / "kiosk_audit.jsonl"
    central_file = tmp_path / "central_audit.jsonl"

    audit_log = OfflineAuditLog(log_path=audit_file)
    audit_log.append_event("Alice", "main_gate", "ALLOW", "Entry")
    audit_log.append_event("Bob", "library", "DENY", "No badge")

    sync_mgr = SyncManager(audit_log=audit_log, central_store_path=central_file)

    # 1. Prepare batch on kiosk
    batch = sync_mgr.prepare_sync_batch("kiosk-test-01")
    assert batch["event_count"] == 2
    assert "batch_signature" in batch

    # 2. Ingest on central server
    receipt = sync_mgr.process_incoming_batch(batch)
    assert receipt["success"] is True
    assert receipt["reconciled_count"] == 2

    # 3. Complete sync on kiosk
    updated = sync_mgr.complete_sync(receipt)
    assert updated == 2
    assert len(audit_log.get_pending_sync_events()) == 0

    # 4. Verify central store has the records
    central_records = sync_mgr.read_central_records()
    assert len(central_records) == 2
    assert central_records[0]["zone"] == "main_gate"
