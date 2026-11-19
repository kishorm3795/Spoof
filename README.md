# HID Hackathon: Face Liveness & Smart Campus Access Kiosk

An enterprise-grade physical access control kiosk prototype built for the **HID Hackathon: "Can You Spot a Spoof?"** incorporating the core problem statement and both follow-up **Surprise Challenges**.

---

## Executive Highlights

| Dimension | Guarantee / Result | Verification Status |
| :--- | :--- | :--- |
| **Decision Latency** | **Mean 1.11 ms, p95 1.47 ms** (Target $\le 2.0\text{ s}$) | **PASSED (1,300x faster than SLA)** |
| **Overall Accuracy** | **98.67%** across 150 test presentations | **PASSED** |
| **Attack Detection Rate** | Printed: **100%**, Screen: **100%**, Video: **92%**, Mask: **100%** | **PASSED across all 4 spoof types** |
| **APCER / BPCER** | APCER: **2.0%**, BPCER: **0.0%** | **PASSED** |
| **Surprise Challenge 1** | Biometric + Campus Schedule Authorization | **PASSED (Allow, Step-Up, Deny)** |
| **Surprise Challenge 2** | Offline Air-Gap Mode with Safe Fail-Secure Access | **PASSED (TOTP Fallback & HMAC Sync)** |

---

## 1. Challenge 1: Multi-Spoof Passive Liveness Detection

Distinguishes live human faces from presentation attacks within **2 seconds** across 4 attack vectors:
1. **Printed Photographs**: 2D Fast Fourier Transform (FFT) spatial frequency density analysis and Laplacian micro-texture variance detect high-frequency print loss and paper halftone grain.
2. **Screen Replays (Photo on Phone/Tablet)**: Specular reflection highlight detection and blue-phosphor spectral temperature bias detect electronic display glass glare.
3. **Video Replays**: 2D periodic Moire interference peak analysis identifies camera sensor interaction with digital display pixel matrices.
4. **3D / Printed Masks**: Surface normal gradient disparity and aperture rim edge discontinuities detect planar paper cutouts and rigid silicone/resin masks.

### Three-Tier Decision Engine
- `ALLOW`: Genuine physical presence confirmed AND identity verified AND campus schedule authorized.
- `REQUEST VERIFICATION`: Borderline confidence (suboptimal lighting, borderline texture, or after-hours grace period). Triggers secondary step-up verification: 6-digit TOTP, active landmark action, or camera recapture.
- `DENY`: Presentation attack identified, identity mismatch, unauthorized zone, or after-hours curfew.

---

## 2. Surprise Challenge 1: Access with Campus Schedule

$$\text{Decision} = \text{Biometric Result} + \text{Campus Access Schedule} \longrightarrow \text{ALLOW / STEP-UP VERIFICATION / DENY}$$

- **Comprehensive University Role Hierarchy**:
  - `admin`: Campus Administrator with universal executive clearance across all facilities, offices, and server rooms.
  - `teacher` / `faculty`: Teachers & Professors with access to classrooms, faculty lounge, library, and 24/7 research lab privileges.
  - `student`: Standard students with classroom, dorm, library, and lab daytime curfew (08:00–20:00, grace to 22:00 with step-up OTP).
  - `user`: General campus users / registered members with perimeter concourse and library access.
  - `researcher`: Graduate & Lab Researchers with 24/7 dedicated engineering and research cluster access.
  - `dean`: Academic Deans with senior executive academic clearance.
  - `staff`: IT & Operational Staff with administrative office and datacenter maintenance clearance.
  - `security`: Campus Security Personnel with 24/7 universal clearance and emergency perimeter override.
  - `visitor`, `contractor`, `maintenance`: Public daytime pass and scheduled operational utility access.
- **Facility Zones**:
  - `main_gate`: 24/7 access for campus members; daytime pass for visitors.
  - `engineering_lab`: 08:00–20:00 regular access; 20:00–22:00 after-hours grace (requires `STEP-UP VERIFICATION`); 22:00–08:00 curfew (`DENY`). Teachers and researchers receive 24/7 research privileges.
  - `library`: 07:00–23:00 everyday for students, faculty, and campus users.
  - `admin_office`: Mon–Fri 08:30–17:30 business hours (restricted to staff, deans, teachers, admin, security).
  - `dormitory`: 24/7 residential access for students, admin, security, and maintenance.
  - `server_room_high_security`: Strict IT staff, administrator, and security access only (locks down fail-secure when offline).
  - `faculty_lounge`: 06:00–23:00 for teachers, faculty, deans, admin, and staff.
  - `classroom_hall`: 07:30–21:30 for teachers, students, security, and academic staff.
- **Emergency Lockdowns & Holidays**: Configurable dynamic curfew overrides.

---

## 3. Surprise Challenge 2: Offline Mode with Safe Access

When network connection to central cloud services is severed:
1. **Safe Local Decision Process**: Operates against local cached biometric embeddings and local facility schedule policies.
2. **Avoid Unsafe Automatic Access**: Fail-secure policy enforces $+15\%$ stricter biometric threshold and locks down high-security facilities (`server_room_high_security`).
3. **Emergency Fallback Verification**: RFC 6238 Time-based One-Time Passwords (TOTP) and Master Security Override PINs (`994821`) provide verifiable offline fallback.
4. **Minimal Temporary Storage**: Kiosk **NEVER** writes face photos or raw embeddings to offline storage. Stores only pseudonymized HMAC records with append-only cryptographic hash chaining ($H_i = \text{SHA256}(H_{i-1} \parallel \text{Event}_i)$).
5. **Reconnection & Synchronization**: Upon network restoration, batch reconciliation dispatches events to `/sync/offline-logs`, verifies signatures, updates central audit logs, and clears local queues.

---

## 4. Setup & Running the Kiosk

### Prerequisites
- Python 3.11+
- Virtual environment created and activated

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the FastAPI Backend
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 3. Start the Frontend Kiosk Server (in second terminal)
cd frontend
python3 -m http.server 5500

# 4. Open in Browser
# Navigate to: http://localhost:5500/kiosk.html
```

---

## 5. API Reference

| Endpoint | Method | Tag | Description |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | system | Server, PCA model, and subsystem readiness |
| `/access/evaluate` | `POST` | kiosk | Complete fusion: Biometrics + Liveness + Schedule + Offline |
| `/liveness/inspect` | `POST` | liveness | Sub-2s passive anti-spoofing inspection |
| `/register` | `POST` | faces | Enrolls face photo with assigned role & schedule preset |
| `/users` | `GET` | faces | Lists enrolled users with role and schedule metadata |
| `/roles` | `GET` | schedule | Returns university role catalog, badges, and privilege metadata |
| `/access/step-up/verify`| `POST` | step-up | Validates 6-digit TOTP, action challenge, or supervisor PIN |
| `/access/step-up/current-otp`| `GET` | step-up | Returns active RFC 6238 TOTP code for test evaluation |
| `/schedule/policies` | `GET` | schedule | Returns all campus zone hours and lockdown states |
| `/schedule/lockdown` | `POST` | schedule | Activates/lifts emergency facility lockdown |
| `/sync/offline-logs` | `POST` | sync | Ingests and reconciles offline kiosk audit batches |
| `/sync/trigger-local` | `POST` | sync | Triggers kiosk-side synchronization of pending offline logs |
| `/sync/status` | `GET` | sync | Reports pending queue count and cryptographic chain validity |
| `/benchmark/run` | `GET` | benchmark | Runs automated benchmark across 150 presentations |

---

## 6. Running the Test Suite

```bash
# Run all 26 automated unit and integration tests:
pytest tests/ -v

# Run performance benchmark:
PYTHONPATH=backend python backend/benchmark.py
```
