"""
tests/test_api.py
-----------------
End-to-end integration test suite for the FastAPI application:
- Health and status endpoints
- Registration and PCA verification pipeline
- Passive anti-spoofing inspection (/liveness/inspect)
- Unified Kiosk Evaluation (/access/evaluate) fusing biometric + campus schedule
- Step-Up verification workflow (/access/step-up/verify)
- Offline audit logging and synchronization (/sync/trigger-local, /sync/status)
"""

import io
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
try:
    if "pytest" in sys.modules:
        import pytest
        fixture = pytest.fixture
    else:
        def fixture(*args, **kwargs):
            def decorator(f):
                return f
            return decorator if (args and callable(args[0])) else decorator
except Exception:
    def fixture(*args, **kwargs):
        def decorator(f):
            return f
        return decorator if (args and callable(args[0])) else decorator

from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from main import app, pca, store, audit_log, sync_manager, totp_fallback
import config


def create_test_face_image(seed: int, color_val: int = 128) -> bytes:
    """Generate a synthetic 100x100 face-like test image."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (100, 100), color=(color_val, color_val, color_val))
    draw = ImageDraw.Draw(img)
    # Head contour
    draw.ellipse([20, 20, 80, 80], outline=(200, 200, 200), fill=(color_val + 20, color_val + 20, color_val + 20))
    # Eyes
    draw.ellipse([35, 40, 45, 50], fill=(50, 50, 50))
    draw.ellipse([55, 40, 65, 50], fill=(50, 50, 50))
    # Mouth
    draw.rectangle([40, 65, 60, 70], fill=(80, 80, 80))
    # Add subtle unique pattern based on seed
    pattern = (rng.integers(0, 30, (100, 100, 3))).astype(np.uint8)
    img_arr = np.clip(np.array(img, dtype=np.int16) + pattern, 0, 255).astype(np.uint8)
    final_img = Image.fromarray(img_arr)

    buf = io.BytesIO()
    final_img.save(buf, format="PNG")
    return buf.getvalue()


@fixture(autouse=True)
def clean_test_environment():
    """Clean data & model files and reset in-memory singletons before each test."""
    def _reset():
        if config.RAW_FACES_PATH.exists():
            config.RAW_FACES_PATH.unlink()
        if config.EIGENFACES_PATH.exists():
            config.EIGENFACES_PATH.unlink()
        vec_store = config.BASE_DIR / "data" / "vector_store.npz"
        if vec_store.exists():
            vec_store.unlink()
        if config.OFFLINE_AUDIT_LOG_PATH.exists():
            config.OFFLINE_AUDIT_LOG_PATH.unlink()

        # Reset in-memory state of singletons
        pca.is_trained = False
        pca.mean_face = np.empty((0,), dtype=np.float32)
        pca.U = np.empty((0, 0), dtype=np.float32)
        store._names = []
        store._vectors = np.empty((0,), dtype=np.float32)

    _reset()
    yield
    _reset()


def test_health_initial():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model_ready"] is False
    assert data["users"] == 0
    assert data["anti_spoofing"] is True
    assert data["schedule"] is True
    assert data["offline_ready"] is True


def test_registration_and_verification_pipeline():
    client = TestClient(app)

    # Register Alice
    alice_img = create_test_face_image(seed=1, color_val=100)
    res_reg1 = client.post(
        "/register",
        data={"name": "Alice"},
        files={"image": ("alice.png", alice_img, "image/png")},
    )
    assert res_reg1.status_code == 200
    assert res_reg1.json()["total_users"] == 1
    assert res_reg1.json()["model_ready"] is False  # Needs >= 2 faces

    # Register Bob
    bob_img = create_test_face_image(seed=2, color_val=180)
    res_reg2 = client.post(
        "/register",
        data={"name": "Bob"},
        files={"image": ("bob.png", bob_img, "image/png")},
    )
    assert res_reg2.status_code == 200
    assert res_reg2.json()["total_users"] == 2
    assert res_reg2.json()["model_ready"] is True

    # Verify Alice
    res_ver = client.post(
        "/verify",
        files={"image": ("alice_test.png", alice_img, "image/png")},
    )
    assert res_ver.status_code == 200
    data_ver = res_ver.json()
    assert data_ver["match"] is True
    assert data_ver["name"] == "Alice"


def test_liveness_inspect_endpoint():
    client = TestClient(app)
    face_img = create_test_face_image(seed=42, color_val=140)

    res = client.post(
        "/liveness/inspect",
        files={"image": ("face.png", face_img, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()
    assert "is_live" in data
    assert "liveness_score" in data
    assert "decision_outcome" in data
    assert "latency_ms" in data
    assert data["within_sla"] is True
    assert data["latency_ms"] < 2000.0


def test_unified_access_evaluate_endpoint():
    client = TestClient(app)

    # Enroll two users
    alice_img = create_test_face_image(seed=11, color_val=110)
    bob_img = create_test_face_image(seed=22, color_val=170)
    client.post("/register", data={"name": "Alice"}, files={"image": ("a.png", alice_img, "image/png")})
    client.post("/register", data={"name": "Bob"}, files={"image": ("b.png", bob_img, "image/png")})

    # Test Kiosk Access for Alice (Tuesday 14:00 at Main Gate)
    res = client.post(
        "/access/evaluate",
        data={
            "role": "student",
            "zone": "main_gate",
            "simulated_time": "2026-11-17T14:00:00",
        },
        files={"image": ("alice.png", alice_img, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()
    assert "final_decision" in data
    assert "biometric" in data
    assert "schedule" in data
    assert data["within_sla"] is True
    assert data["total_latency_ms"] < 2000.0


def test_offline_mode_in_access_evaluate():
    client = TestClient(app)
    alice_img = create_test_face_image(seed=11, color_val=110)
    bob_img = create_test_face_image(seed=22, color_val=170)
    client.post("/register", data={"name": "Alice"}, files={"image": ("a.png", alice_img, "image/png")})
    client.post("/register", data={"name": "Bob"}, files={"image": ("b.png", bob_img, "image/png")})

    # Evaluate in offline mode for server room (should fail-secure DENY)
    res = client.post(
        "/access/evaluate",
        data={
            "role": "staff",
            "zone": "server_room_high_security",
            "offline": True,
            "simulated_time": "2026-11-17T14:00:00",
        },
        files={"image": ("alice.png", alice_img, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["final_decision"] == "DENY"
    assert data["offline_mode"] is True
    assert "fail-secure" in data["reason"].lower()


def test_step_up_verification_endpoint():
    client = TestClient(app)

    # 1. Test with Master Override PIN
    res_pin = client.post(
        "/access/step-up/verify",
        data={
            "verification_type": "supervisor_pin",
            "code": "994821",
            "user_name": "Alice",
            "zone": "main_gate",
        },
    )
    assert res_pin.status_code == 200
    assert res_pin.json()["success"] is True
    assert res_pin.json()["final_decision"] == "ALLOW"

    # 2. Test with RFC 6238 TOTP
    cur_otp = totp_fallback.generate_token()
    res_totp = client.post(
        "/access/step-up/verify",
        data={
            "verification_type": "otp",
            "code": cur_otp,
            "user_name": "Alice",
            "zone": "engineering_lab",
        },
    )
    assert res_totp.status_code == 200
    assert res_totp.json()["success"] is True

    # 3. Test invalid code -> DENY
    res_bad = client.post(
        "/access/step-up/verify",
        data={
            "verification_type": "otp",
            "code": "000000",
            "user_name": "Alice",
            "zone": "main_gate",
        },
    )
    assert res_bad.status_code == 200
    assert res_bad.json()["success"] is False
    assert res_bad.json()["final_decision"] == "DENY"


def test_sync_endpoints_flow():
    client = TestClient(app)

    # Trigger sync when empty
    res_empty = client.post("/sync/trigger-local")
    assert res_empty.status_code == 200
    assert res_empty.json()["synced_count"] == 0

    # Append an offline event directly
    audit_log.append_event("Alice", "main_gate", "ALLOW", "Offline test")

    # Check status
    res_status = client.get("/sync/status")
    assert res_status.status_code == 200
    assert res_status.json()["local_pending_sync_count"] == 1
    assert res_status.json()["chain_integrity_valid"] is True

    # Trigger sync
    res_sync = client.post("/sync/trigger-local")
    assert res_sync.status_code == 200
    assert res_sync.json()["synced_count"] == 1

    # Check status again
    res_status2 = client.get("/sync/status")
    assert res_status2.json()["local_pending_sync_count"] == 0


def test_roles_catalog_endpoint():
    client = TestClient(app)
    res = client.get("/roles")
    assert res.status_code == 200
    data = res.json()
    assert "roles" in data
    role_ids = {r["id"] for r in data["roles"]}
    assert "admin" in role_ids
    assert "teacher" in role_ids
    assert "student" in role_ids
    assert "user" in role_ids

    # Verify badge colors and properties
    admin_meta = next(r for r in data["roles"] if r["id"] == "admin")
    assert admin_meta["badge_color"] == "#A855F7"
    assert admin_meta["universal_clearance"] is True

    teacher_meta = next(r for r in data["roles"] if r["id"] == "teacher")
    assert teacher_meta["badge_color"] == "#3B82F6"
    assert "research" in teacher_meta["description"].lower()


def test_registration_with_assigned_role_and_auto_detection():
    client = TestClient(app)

    # 1. Register Dr. Marcus Vance with role="teacher" and schedule="lab_hours"
    vance_img = create_test_face_image(seed=55, color_val=130)
    res1 = client.post(
        "/register",
        data={"name": "Dr. Marcus Vance", "role": "teacher", "schedule_preset": "lab_hours"},
        files={"image": ("vance.png", vance_img, "image/png")},
    )
    assert res1.status_code == 200
    assert res1.json()["role"] == "teacher"

    # 2. Register Alice with role="student" and schedule="campus_hours"
    alice_img = create_test_face_image(seed=66, color_val=150)
    res2 = client.post(
        "/register",
        data={"name": "Alice Chen", "role": "student", "schedule_preset": "campus_hours"},
        files={"image": ("alice.png", alice_img, "image/png")},
    )
    assert res2.status_code == 200
    assert res2.json()["role"] == "student"

    # Verify metadata in GET /users
    users_res = client.get("/users")
    assert users_res.status_code == 200
    meta = users_res.json()["metadata"]
    assert meta["Dr. Marcus Vance"]["role"] == "teacher"
    assert meta["Alice Chen"]["role"] == "student"

    # 3. Test /access/evaluate with role="auto" for Dr. Marcus Vance at 23:45 in engineering_lab
    # Teacher has 24/7 research lab privileges -> should be ALLOW with auto-detected role "teacher"
    res_eval = client.post(
        "/access/evaluate",
        data={
            "role": "auto",
            "zone": "engineering_lab",
            "simulated_time": "2026-11-17T23:45:00",
        },
        files={"image": ("vance_test.png", vance_img, "image/png")},
    )
    assert res_eval.status_code == 200
    data_eval = res_eval.json()
    assert data_eval["final_decision"] == "ALLOW"
    assert data_eval["schedule"]["role"] == "teacher"
    assert data_eval["schedule"]["role_auto_detected"] is True
    assert data_eval["schedule"]["enrolled_role"] == "teacher"


if __name__ == "__main__":
    test_list = [
        test_health_initial,
        test_registration_and_verification_pipeline,
        test_liveness_inspect_endpoint,
        test_unified_access_evaluate_endpoint,
        test_offline_mode_in_access_evaluate,
        test_step_up_verification_endpoint,
        test_sync_endpoints_flow,
        test_roles_catalog_endpoint,
        test_registration_with_assigned_role_and_auto_detection,
    ]
    for t in test_list:
        clean_fn = clean_test_environment()
        next(clean_fn)
        try:
            t()
            print(f"PASS: {t.__name__}", flush=True)
        finally:
            try:
                next(clean_fn)
            except StopIteration:
                pass
    print(f"\nAll {len(test_list)} API tests successfully passed!", flush=True)
