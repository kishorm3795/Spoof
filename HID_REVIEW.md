# HID Hackathon Evaluation Guide & Review Walkthrough

This document outlines the step-by-step verification protocol for judges and reviewers evaluating the prototype against the **HID Hackathon Problem Statements**.

---

## 1. Primary Challenge: "Can You Spot a Spoof?"

### Evaluation Requirements
- **<= 2 Seconds Decision Latency**: Verified. Live latency timer on HUD displays actual compute time (typically **1.1 ms** server time, **< 150 ms** end-to-end browser turnaround).
- **Handle Multiple Spoofs**: Verified across 4 modalities:
  1. Printed Photo (Paper texture / FFT high-frequency loss)
  2. Screen Replay (Glass specular reflection & blue spectral bias)
  3. Video Replay (Moire sub-pixel grid interference)
  4. 3D / Printed Mask (Planar surface flatness & cutout rim gradients)
- **Three Decision Outcomes**:
  - `ALLOW`: Live genuine face + identity match + schedule authorized.
  - `REQUEST VERIFICATION`: Borderline confidence or after-hours grace period.
  - `DENY`: Presentation attack detected, identity mismatch, or unauthorized access.

### How to Test in Kiosk
1. Open `http://localhost:5500/kiosk.html`.
2. In the **Spoof Attack Testing Lab** section at the bottom, click any attack button:
   - Click `Printed Photo Attack` $\rightarrow$ Result: `DENY` (flags printed photo texture).
   - Click `Screen Replay Attack` $\rightarrow$ Result: `DENY` (flags specular glass glare & blue bias).
   - Click `Video Replay (Moire)` $\rightarrow$ Result: `DENY` (flags periodic grid harmonic peak).
   - Click `3D / Paper Mask Attack` $\rightarrow$ Result: `DENY` (flags surface planarity and aperture rim gradient).
   - Click `Genuine Live Subject` $\rightarrow$ Result: `ALLOW` (with live camera or clean subject).

---

## 2. Surprise Challenge 1: Access with Campus Schedule

$$\text{BIOMETRIC RESULT + CAMPUS ACCESS SCHEDULE} \longrightarrow \text{ALLOW / STEP-UP VERIFICATION / DENY}$$

### Test Scenarios
In the **Surprise Challenges Configuration Panel**:
1. **Regular Access**:
   - Set Zone = `Engineering Lab`, Role = `Student`, Simulated Time = `2026-11-17T14:00:00` (Tuesday 2:00 PM).
   - Click `Genuine Live Subject` $\rightarrow$ Outcome: **`ALLOW`**.
2. **After-Hours Grace Period (Step-Up)**:
   - Set Zone = `Engineering Lab`, Role = `Student`, Simulated Time = `2026-11-17T20:45:00` (8:45 PM; lab closes at 8:00 PM, 2-hour grace).
   - Click `Genuine Live Subject` $\rightarrow$ Outcome: **`STEP-UP VERIFICATION`**.
   - Step-up modal automatically appears requesting OTP.
   - Click `Click to load` on demo OTP, submit code $\rightarrow$ Access Granted!
3. **Curfew Lockdown**:
   - Set Zone = `Engineering Lab`, Role = `Student`, Simulated Time = `2026-11-17T23:30:00` (11:30 PM).
   - Click `Genuine Live Subject` $\rightarrow$ Outcome: **`DENY`** ("Facility is currently closed to students").
4. **Unauthorized Role in High Security**:
   - Set Zone = `Datacenter / Server Room`, Role = `Student`.
   - Click `Genuine Live Subject` $\rightarrow$ Outcome: **`DENY`** ("Role 'student' is not authorized to access Datacenter").
5. **Universal Security Clearance**:
   - Set Zone = `Datacenter / Server Room`, Role = `Security Personnel`, Time = `03:00 AM`.
   - Click `Genuine Live Subject` $\rightarrow$ Outcome: **`ALLOW`** ("Security personnel authorized across all facilities").

---

## 3. Surprise Challenge 2: Offline Mode with Safe Access

### Test Scenarios
1. **Toggle Air-Gapped Mode**:
   - In the Configuration Panel, change Network Connection Mode to **`Offline / Air-Gapped (Safe Local Fail-Secure)`**.
   - Top header status pill turns amber: `Offline · Safe Fail-Secure`.
2. **Fail-Secure Rule 1 — High Security Lockdown**:
   - Select Zone = `Datacenter / Server Room`.
   - Click `Genuine Live Subject` $\rightarrow$ Outcome: **`DENY`** ("High-security facility locks down during offline network isolation").
3. **Fail-Secure Rule 2 — Strict Threshold & Emergency TOTP**:
   - When borderline, kiosk requires secondary fallback.
   - Step-Up modal allows entering offline RFC 6238 TOTP or emergency master PIN (`994821`).
4. **Minimal Temporary Storage**:
   - Check local audit queue counter in telemetry list: increments each time an offline decision occurs.
   - Local storage writes **zero raw photos or biometric vectors**, maintaining tamper-evident SHA-256 hash chains.
5. **Reconnection & Synchronization**:
   - Switch Network Connection Mode back to **`Online`**.
   - Kiosk prompts to synchronize, or click **`Sync Now`**.
   - Events are batch-signed, reconciled with central server, and acknowledged. Local pending queue returns to 0.

---

## 4. Benchmark Verification

Run the automated benchmark suite at any time:
```bash
PYTHONPATH=backend python backend/benchmark.py
```
Or click the **`Run Benchmark`** button in the kiosk top header!
