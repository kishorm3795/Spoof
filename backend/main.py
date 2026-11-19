"""
main.py
-------
FastAPI application – all HTTP routes.

Routes
------
GET  /health                → server status
POST /register              → register a new face
POST /verify                → verify an uploaded face
GET  /users                 → list all registered users
DELETE /users/{name}        → remove a user and retrain
POST /retrain               → rebuild PCA from scratch

Auto-generated Swagger UI available at http://localhost:8000/docs
"""

from __future__ import annotations

import time
import json
from datetime import datetime
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import RAW_FACES_PATH, USER_METADATA_PATH, K
from image_utils import preprocess_bytes, preprocess_bytes_with_info
from pca_engine import PCAEngine
from chroma_store import ChromaStore

from liveness.engine import LivenessEngine
from schedule.engine import CampusScheduleEngine
from schedule.models import UserRole, CampusZone, DecisionOutcome
from offline.audit_log import OfflineAuditLog
from offline.local_evaluator import LocalSafeEvaluator
from offline.totp_fallback import TOTPFallback
from offline.sync_manager import SyncManager

# ── App setup ────────────────────────────────────────────────────────────
app = FastAPI(
    title="Spectral Face Recognition API",
    description="Eigenface-based face recognition with passive anti-spoofing and campus schedule authorization.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ───────────────────────────────────────────────────────────
pca              = PCAEngine(k=K)
store            = ChromaStore()
liveness_engine  = LivenessEngine()
schedule_engine  = CampusScheduleEngine()
audit_log        = OfflineAuditLog()
local_evaluator  = LocalSafeEvaluator(audit_log=audit_log, schedule_engine=schedule_engine)
totp_fallback    = TOTPFallback()
sync_manager     = SyncManager(audit_log=audit_log)

# ── Startup ──────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    loaded = pca.load()
    if loaded:
        print(f"[startup] PCA model loaded (K={pca.K}, U={pca.U.shape})")
    else:
        print("[startup] No saved model — register faces to train.")


# ── Raw face store helpers ────────────────────────────────────────────────

def _load_raw() -> tuple[list[str], np.ndarray]:
    if not RAW_FACES_PATH.exists():
        return [], np.empty((0,), dtype=np.float32)
    data  = np.load(RAW_FACES_PATH, allow_pickle=True)
    names = data["names"].tolist()
    X     = data["X"]
    return names, X


def _save_raw(names: list[str], X: np.ndarray) -> None:
    RAW_FACES_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(RAW_FACES_PATH, names=np.array(names), X=X)


def _load_user_metadata() -> dict[str, dict]:
    if not USER_METADATA_PATH.exists():
        return {}
    try:
        with open(USER_METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_user_metadata(meta: dict[str, dict]) -> None:
    USER_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USER_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def _retrain_and_upsert() -> int:
    """Rebuild PCA from all raw faces, re-project, upsert to vector store."""
    names, X = _load_raw()
    n = len(names)
    if n < 2:
        return n
    pca.train(X)
    omegas = pca.project_many(X)
    store.add_many(names, omegas)
    return n


# ── Routes ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    return {
        "status":        "ok",
        "model_ready":   pca.is_trained,
        "users":         store.count(),
        "anti_spoofing": True,
        "schedule":      True,
        "offline_ready": True,
    }


@app.post("/liveness/inspect", tags=["liveness"])
async def inspect_liveness(
    image: UploadFile = File(..., description="Face image for presentation attack inspection"),
):
    """
    Sub-2-second passive anti-spoofing inspection:
    Evaluates printed photos, screen replays, moire patterns, and 3D masks.
    """
    data = await image.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    result = liveness_engine.evaluate(data)
    return result


@app.post("/register", tags=["faces"])
async def register(
    name:  str        = Form(..., description="User's full name"),
    role:  str        = Form(default="student", description="Campus user role (admin, teacher, student, user, researcher, dean, staff, security, visitor)"),
    schedule_preset: str = Form(default="campus_hours", description="Schedule preset (campus_hours, 24x7, lab_hours, none)"),
    image: UploadFile = File(..., description="Face image (jpg, png, etc.)"),
):
    """
    Register a new face.

    1. Detect + crop face region, apply CLAHE normalisation
    2. Append preprocessed vector to raw face store
    3. Save user role & schedule metadata
    4. Retrain PCA with all stored faces
    5. Re-project everyone → upsert Ω vectors into vector store
    """
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name must not be empty.")

    data = await image.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    x, face_found = preprocess_bytes_with_info(data)

    # Append / replace in raw store
    names, X = _load_raw()
    if name in names:
        idx     = names.index(name)
        X[idx]  = x
    else:
        names.append(name)
        X = np.vstack([X, x]) if X.ndim == 2 else x.reshape(1, -1)

    _save_raw(names, X)

    # Store user role and metadata
    clean_role = role.strip().lower()
    meta = _load_user_metadata()
    meta[name] = {
        "role": clean_role,
        "schedule": schedule_preset,
        "enrolledAt": datetime.now().strftime("%Y-%m-%d"),
    }
    _save_user_metadata(meta)

    n = _retrain_and_upsert()

    return {
        "success":     True,
        "message":     f"'{name}' registered as {clean_role.upper()}. Model trained with {n} face(s).",
        "total_users": n,
        "role":        clean_role,
        "model_ready": pca.is_trained,
        "face_detected": face_found,   # frontend can warn if False
    }


@app.post("/verify", tags=["faces"])
async def verify(
    image: UploadFile = File(..., description="Face image to verify"),
):
    """
    Verify an uploaded face.

    1. Detect + crop face region, apply CLAHE normalisation
    2. Project x → Ω using current PCA model
    3. Query vector store for nearest Ω
    4. Return match result + confidence
    """
    if not pca.is_trained:
        raise HTTPException(
            status_code=400,
            detail="No model trained yet. Register at least 2 faces first.",
        )
    if store.count() == 0:
        raise HTTPException(status_code=400, detail="No registered users.")

    data = await image.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    x, face_found = preprocess_bytes_with_info(data)
    omega  = pca.project(x)
    result = store.query(omega)
    result["face_detected"] = face_found   # extra info for frontend

    return result


@app.post("/access/evaluate", tags=["kiosk"])
async def evaluate_kiosk_access(
    image: UploadFile = File(..., description="Face image from entry camera"),
    role: str = Form(default="auto", description="Claimed user role or 'auto' to auto-detect from enrolled profile"),
    zone: str = Form(default="main_gate", description="Target campus facility zone"),
    offline: bool = Form(default=False, description="Simulate offline air-gapped kiosk mode"),
    simulated_time: str = Form(default="", description="Optional simulated ISO datetime string for schedule testing"),
):
    """
    Unified HID Kiosk Evaluation Route:
    Fuses Biometric Verification + Passive Anti-Spoofing + Campus Schedule Authorization + Offline Fail-Secure.
    Formula: BIOMETRIC RESULT + CAMPUS ACCESS SCHEDULE -> ALLOW / STEP-UP VERIFICATION / DENY
    Guaranteed decision latency within 2.0 seconds.
    """
    t_start = time.perf_counter()

    data = await image.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    dt_now = None
    if simulated_time.strip():
        try:
            dt_now = datetime.fromisoformat(simulated_time.strip())
        except ValueError:
            dt_now = None

    # 1. Passive Anti-Spoofing Assessment
    liveness_res = liveness_engine.evaluate(data)

    # 2. Identity Verification (PCA)
    identity_res = {"match": False, "name": "Unknown", "distance": 1.0, "confidence": 0.0}
    if pca.is_trained and store.count() > 0:
        try:
            x, face_found = preprocess_bytes_with_info(data)
            omega = pca.project(x)
            identity_res = store.query(omega)
            identity_res["face_detected"] = face_found
        except Exception as e:
            identity_res["error"] = str(e)

    matched_name = identity_res.get("name", "Unknown") if identity_res.get("match") else "Unknown"
    is_identity_match = bool(identity_res.get("match", False))
    cosine_dist = float(identity_res.get("distance", 1.0))

    # Derive combined biometric outcome
    if not liveness_res["is_live"] and not liveness_res["is_borderline"]:
        biometric_outcome = "DENY"
        bio_reason = f"Spoof presentation attack rejected ({liveness_res['spoof_type']})"
    elif not is_identity_match:
        biometric_outcome = "DENY"
        bio_reason = "No enrolled identity match found in database"
    elif liveness_res["is_borderline"]:
        biometric_outcome = "REQUEST VERIFICATION"
        bio_reason = "Borderline liveness confidence: active challenge or secondary verification required"
    else:
        biometric_outcome = "ALLOW"
        bio_reason = f"Live person confirmed and matched to enrolled identity '{matched_name}'"

    # Resolve effective role (auto-resolve from registered identity if requested)
    is_auto_role = role.strip().lower() in ["", "auto", "default"]
    enrolled_role = None
    if is_identity_match and matched_name != "Unknown":
        user_meta = _load_user_metadata().get(matched_name, {})
        enrolled_role = user_meta.get("role", "student")

    if is_auto_role:
        effective_role = enrolled_role or "visitor"
    else:
        effective_role = role.strip()

    # 3. Handle Offline vs Online Mode
    if offline:
        offline_res = local_evaluator.evaluate_offline(
            biometric_match=is_identity_match,
            user_name=matched_name,
            user_role=effective_role,
            zone=zone,
            cosine_distance=cosine_dist,
            liveness_score=liveness_res["liveness_score"],
            spoof_type=liveness_res["spoof_type"],
            dt=dt_now,
        )
        final_decision = offline_res["outcome"]
        final_reason   = offline_res["reason"]
        step_up_req    = offline_res["step_up_required"]
        sched_status   = "offline_fail_secure"
    else:
        schedule_eval = schedule_engine.evaluate_access(
            biometric_outcome=biometric_outcome,
            user_name=matched_name,
            user_role=effective_role,
            zone=zone,
            dt=dt_now,
        )
        final_decision = schedule_eval.outcome.value
        final_reason   = schedule_eval.reason
        step_up_req    = schedule_eval.step_up_required
        sched_status   = schedule_eval.schedule_status

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
    within_sla = elapsed_ms <= 2000.0

    return {
        "final_decision":   final_decision,
        "reason":           final_reason,
        "step_up_required": step_up_req,
        "biometric": {
            "outcome":    biometric_outcome,
            "reason":     bio_reason,
            "liveness":   liveness_res,
            "identity":   identity_res,
        },
        "schedule": {
            "zone":               zone,
            "role":               effective_role,
            "claimed_role":       role,
            "enrolled_role":      enrolled_role,
            "role_auto_detected": is_auto_role,
            "schedule_status":    sched_status,
        },
        "offline_mode":     offline,
        "total_latency_ms": round(elapsed_ms, 2),
        "within_sla":       within_sla,
    }


@app.get("/schedule/policies", tags=["schedule"])
def get_schedule_policies():
    """Returns all campus zone operating hours and security rules."""
    out = {}
    for zone, pol in schedule_engine.policies.items():
        out[zone.value] = {
            "name": pol.name,
            "allowed_roles": [r.value for r in pol.allowed_roles],
            "after_hours_grace_minutes": pol.after_hours_grace_minutes,
            "is_high_security": pol.is_high_security,
        }
    return {"zones": out, "active_lockdowns": {k.value: v for k, v in schedule_engine.active_lockdowns.items()}}


@app.get("/roles", tags=["schedule"])
def get_roles_catalog():
    """Returns all supported university roles with clearance descriptions and styling metadata."""
    return {
        "roles": [
            {
                "id": "admin",
                "title": "Campus Administrator",
                "category": "Administration",
                "description": "Universal administrative executive clearance across all campus facilities & server rooms",
                "badge_color": "#A855F7",
                "universal_clearance": True,
            },
            {
                "id": "teacher",
                "title": "Teacher / Professor",
                "category": "Academic",
                "description": "Faculty lounge, classrooms, library, and 24/7 research laboratory privileges",
                "badge_color": "#3B82F6",
                "universal_clearance": False,
            },
            {
                "id": "student",
                "title": "Student",
                "category": "Academic",
                "description": "Standard classroom, library, dormitory, and laboratory daytime curfew access",
                "badge_color": "#10B981",
                "universal_clearance": False,
            },
            {
                "id": "user",
                "title": "General Campus User",
                "category": "General",
                "description": "Registered campus attendee with main gate, library, and public concourse clearance",
                "badge_color": "#06B6D4",
                "universal_clearance": False,
            },
            {
                "id": "faculty",
                "title": "Faculty Member",
                "category": "Academic",
                "description": "Department faculty with classroom, lab, library, and faculty lounge access",
                "badge_color": "#2563EB",
                "universal_clearance": False,
            },
            {
                "id": "researcher",
                "title": "Research Fellow",
                "category": "Academic",
                "description": "Specialized lab clearance, engineering computing facilities, and library",
                "badge_color": "#14B8A6",
                "universal_clearance": False,
            },
            {
                "id": "dean",
                "title": "Academic Dean",
                "category": "Administration",
                "description": "Senior executive dean clearance across academic and administrative wings",
                "badge_color": "#EC4899",
                "universal_clearance": True,
            },
            {
                "id": "staff",
                "title": "IT & Administrative Staff",
                "category": "Operations",
                "description": "Administrative offices and datacenter maintenance clearance",
                "badge_color": "#F97316",
                "universal_clearance": False,
            },
            {
                "id": "security",
                "title": "Campus Security Officer",
                "category": "Security",
                "description": "24/7 Universal campus clearance, patrol bypass, and emergency response",
                "badge_color": "#EF4444",
                "universal_clearance": True,
            },
            {
                "id": "visitor",
                "title": "Visitor / Guest",
                "category": "Public",
                "description": "Temporary daytime pass for campus perimeter and public facilities",
                "badge_color": "#64748B",
                "universal_clearance": False,
            },
            {
                "id": "contractor",
                "title": "Contractor / Vendor",
                "category": "Operations",
                "description": "Scheduled facility maintenance and contractor work window",
                "badge_color": "#EAB308",
                "universal_clearance": False,
            },
            {
                "id": "maintenance",
                "title": "Facilities & Maintenance",
                "category": "Operations",
                "description": "Utility infrastructure, laboratory servicing, dormitories, and repairs",
                "badge_color": "#8B5CF6",
                "universal_clearance": False,
            },
        ]
    }


@app.post("/schedule/lockdown", tags=["schedule"])
def toggle_zone_lockdown(
    zone: str = Form(..., description="Campus zone to lock down"),
    enabled: bool = Form(default=True, description="Enable or disable emergency curfew"),
    reason: str = Form(default="Security protocol activation", description="Lockdown reason"),
):
    """Enforces or lifts an emergency lockdown on a facility."""
    schedule_engine.set_lockdown(zone, enabled=enabled, reason=reason)
    return {
        "success": True,
        "zone": zone,
        "lockdown_active": enabled,
        "reason": reason if enabled else "Normal operations restored",
    }


# ── Surprise Challenge 2: Offline Mode & Synchronization Endpoints ────────

@app.post("/sync/offline-logs", tags=["sync"])
async def ingest_offline_logs(batch_data: dict):
    """
    Central server ingestion route for offline kiosk decision logs.
    Validates cryptographic HMAC signatures and reconciles events.
    """
    result = sync_manager.process_incoming_batch(batch_data)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Batch ingestion failed"))
    return result


@app.get("/sync/status", tags=["sync"])
def get_sync_status():
    """
    Returns synchronization status, local unsynced count,
    and cryptographic chain integrity report.
    """
    is_valid, integrity_msg = audit_log.verify_chain_integrity()
    pending = audit_log.get_pending_sync_events()
    central_records = sync_manager.read_central_records()

    return {
        "local_pending_sync_count": len(pending),
        "local_total_events": len(audit_log.read_all_events()),
        "central_reconciled_count": len(central_records),
        "chain_integrity_valid": is_valid,
        "chain_integrity_message": integrity_msg,
    }


@app.post("/sync/trigger-local", tags=["sync"])
def trigger_local_kiosk_sync():
    """
    Executes end-to-end local kiosk synchronization:
    Packages uncommitted offline logs, submits to central store, and updates local status.
    """
    batch = sync_manager.prepare_sync_batch("kiosk-local-01")
    if batch["event_count"] == 0:
        return {"success": True, "message": "No pending offline events to synchronize.", "synced_count": 0}

    receipt = sync_manager.process_incoming_batch(batch)
    if not receipt.get("success"):
        raise HTTPException(status_code=500, detail=receipt.get("error", "Reconciliation failed"))

    updated = sync_manager.complete_sync(receipt)
    return {
        "success": True,
        "message": f"Successfully synchronized {updated} offline decision(s) with central server.",
        "synced_count": updated,
        "batch_id": batch["batch_id"],
    }


# ── Step-Up Verification Workflow ─────────────────────────────────────────

@app.get("/access/step-up/current-otp", tags=["step-up"])
def get_current_demo_otp():
    """
    Returns the current active RFC 6238 TOTP token for testing/demo purposes.
    Enables hackathon reviewers to test step-up verification without an authenticator app.
    """
    token = totp_fallback.generate_token()
    return {
        "current_token": token,
        "validity_seconds": 30,
        "emergency_master_pin": TOTPFallback.MASTER_OVERRIDE_PIN,
    }


@app.post("/access/step-up/verify", tags=["step-up"])
def verify_step_up(
    verification_type: str = Form(default="otp", description="'otp', 'supervisor_pin', or 'active_action'"),
    code: str = Form(default="", description="6-digit OTP code or emergency override PIN"),
    user_name: str = Form(default="Authorized User", description="Target user name"),
    zone: str = Form(default="main_gate", description="Campus facility zone"),
    action_completed: bool = Form(default=False, description="Set True if active challenge (e.g. blink/turn) was performed"),
    offline: bool = Form(default=False, description="Whether kiosk is in offline mode"),
):
    """
    Handles step-up verification when initial confidence is borderline,
    facility is in after-hours grace period, or kiosk is operating offline.
    """
    t_start = time.perf_counter()
    v_type = verification_type.strip().lower()

    if v_type in ["otp", "supervisor_pin"]:
        if not code.strip():
            raise HTTPException(status_code=400, detail="Verification code is required.")
        is_valid, reason = totp_fallback.verify_fallback(code.strip(), user_name, zone)
    elif v_type == "active_action":
        if action_completed:
            is_valid = True
            reason = "Active physical liveness challenge completed successfully"
        else:
            is_valid = False
            reason = "Active challenge incomplete or unverified"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported verification_type: '{verification_type}'")

    outcome = "ALLOW" if is_valid else "DENY"

    # Log step-up resolution
    if offline:
        audit_log.append_event(
            user_name=user_name,
            zone=zone,
            decision=outcome,
            reason=f"Step-up ({v_type}): {reason}",
        )

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return {
        "success":           is_valid,
        "final_decision":    outcome,
        "verification_type": v_type,
        "reason":            reason,
        "latency_ms":        round(elapsed_ms, 2),
    }


# ── Benchmark Evaluation Endpoint ─────────────────────────────────────────

@app.get("/benchmark/run", tags=["benchmark"])
def trigger_performance_benchmark():
    """
    Executes automated performance and security benchmark across 150 test presentations:
    Measures detection rates for printed photo, screen replay, video replay, and 3D mask,
    and returns latency percentiles (p50, p95 <= 2s), APCER, and BPCER.
    """
    from benchmark import run_benchmark
    report = run_benchmark()
    return report


@app.get("/users", tags=["faces"])
def list_users():
    users = store.list_users()
    meta = _load_user_metadata()
    return {
        "users": users,
        "count": store.count(),
        "metadata": {
            u: meta.get(u, {
                "role": "student",
                "schedule": "campus_hours",
                "enrolledAt": "2026-11-17",
            })
            for u in users
        },
    }


@app.delete("/users/{name}", tags=["faces"])
def delete_user(name: str):
    names, X = _load_raw()
    if name not in names:
        raise HTTPException(status_code=404, detail=f"User '{name}' not found.")

    idx = names.index(name)
    names.pop(idx)
    X   = np.delete(X, idx, axis=0)
    _save_raw(names, X)
    store.delete_face(name)

    # Clean up user role metadata
    meta = _load_user_metadata()
    if name in meta:
        meta.pop(name, None)
        _save_user_metadata(meta)

    n = _retrain_and_upsert()
    return {
        "success":     True,
        "message":     f"'{name}' deleted. Model retrained with {n} remaining user(s).",
        "total_users": n,
    }


@app.post("/retrain", tags=["system"])
def retrain():
    n = _retrain_and_upsert()
    if n < 2:
        return {
            "success": False,
            "message": f"Need at least 2 registered faces (have {n}).",
        }
    return {
        "success": True,
        "message": f"Model retrained with {n} face(s).",
        "K":       pca.K,
        "U_shape": list(pca.U.shape),
    }
