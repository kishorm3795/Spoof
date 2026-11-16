# HID Hackathon Specification: Face Liveness & Surprise Challenges

## Executive Summary

This specification documents the complete architectural design, mathematical models, and operational guarantees for the **HID Hackathon: Face Liveness Detection & Smart Campus Access Kiosk**.

The system addresses the primary challenge and both surprise challenges:
1. **Primary Challenge — Can You Spot a Spoof?**: Sub-2-second face liveness detection and identity authentication resilient against printed photos, screen replays, video replays, and 3D/printed masks.
2. **Surprise Challenge 1 — Access with Campus Schedule**: Integration of biometric verification results with multi-zone, role-based campus schedules (`BIOMETRIC RESULT + CAMPUS ACCESS SCHEDULE → ALLOW / STEP-UP VERIFICATION / DENY`).
3. **Surprise Challenge 2 — Offline Mode with Safe Access**: Air-gapped fail-secure kiosk operation, privacy-preserving local audit logging, emergency TOTP fallback, and reconciliation upon reconnection.

---

## 1. Primary Challenge Architecture: Multi-Spoof Passive Liveness Detection

### 1.1 The Operational Guarantee
- **Decision Latency**: $\le 2.0$ seconds end-to-end (sensor capture to access actuation).
- **Dual Verification**: Both **liveness** (proof of physical presence) and **identity** (spectral biometric match) must be validated.
- **Three-Tier Decision Engine**:
  - `ALLOW`: Live genuine person detected AND identity verified AND campus schedule authorized.
  - `REQUEST VERIFICATION`: Low confidence (e.g., suboptimal lighting, borderline texture score, or after-hours schedule grace window). System requests secondary step: 6-digit OTP, active landmark challenge, or camera recapture.
  - `DENY`: Presentation attack detected, identity mismatch, or unauthorized campus schedule access.

### 1.2 Spoof Types & Detection Methods

| Attack Vector | Physical Manifestation | Algorithmic Detection Principle |
| :--- | :--- | :--- |
| **Printed Photograph** | 2D planar surface, paper grain/halftone, absence of micro-depth, cut edges | 2D Fourier high-frequency attenuation, gradient surface normal coplanarity, Laplacian sharpness ratio |
| **Screen Replay (Photo)** | Pixel grid raster, specular glass reflections, blue-shifted chromaticity | 2D Moire pattern frequency peak detection, specular highlight clipping, RGB channel histogram variance |
| **Video Replay** | Repeating temporal loops, screen bezel contrast, unnatural motion dynamics | Temporal optical variance, frame-to-frame micro-texture fluctuation, display bezel edge bounding |
| **3D / Printed Mask** | Rigid boundary discontinuity, abnormal depth gradient around ocular/oral cavities | Geometric disparity estimation, eye/mouth rim sharpness anomalies, surface reflectance uniformity |

---

## 2. Surprise Challenge 1: Campus Schedule Access Engine

A live, recognized person is **not automatically authorized**. Access clearance requires dynamic evaluation of user identity, role, target zone, and current temporal constraints.

$$\text{Decision} = f(\text{Biometric Outcome}, \text{Role}, \text{Zone}, \text{Timestamp})$$

### 2.1 Role & Zone Matrix

| Role | Permitted Zones | Standard Hours | After-Hours Policy |
| :--- | :--- | :--- | :--- |
| `student` | Main Gate, Library, Dorms | 07:00 – 21:00 | Library/Dorms: 24/7. Labs: Step-up (21:00–23:00), Deny (23:00–07:00) |
| `faculty` | All Academic & Lab Zones | 24/7 | Always `ALLOW` across academic facilities |
| `staff` | Admin Offices, Main Gate | 08:00 – 19:00 | Step-up verification for off-hours maintenance |
| `visitor` | Main Gate, Visitor Center | 09:00 – 17:00 | Strict `DENY` outside scheduled visitation window |
| `contractor`| Assigned Worksite | 07:00 – 18:00 | Pre-scheduled windows only; otherwise `DENY` |
| `security` | All Zones (incl. Server Room) | 24/7 | `ALLOW` with audit logging |

### 2.2 Decision Matrix Fusion

```
               Biometric Result
               ┌───────────────────────┬─────────────────────────┬───────────────────────┐
               │ ALLOW                 │ REQUEST VERIFICATION    │ DENY                  │
┌──────────────┼───────────────────────┼─────────────────────────┼───────────────────────┤
│ Schedule In  │ ALLOW                 │ REQUEST VERIFICATION    │ DENY                  │
│ Schedule Mod │ STEP-UP VERIFICATION  │ REQUEST VERIFICATION    │ DENY                  │
│ Schedule Out │ DENY                  │ DENY                    │ DENY                  │
└──────────────┴───────────────────────┴─────────────────────────┴───────────────────────┘
```

---

## 3. Surprise Challenge 2: Offline Mode with Safe Access

When network connectivity to the central identity service is lost:

1. **Safe Local Decision Process**:
   - The kiosk operates using a local secure cache of user feature embeddings and hashed credentials.
   - Local schedule policies evaluate permissions locally without network roundtrips.
2. **Fail-Secure Architecture**:
   - Stricter acceptance thresholds ($+15\%$ confidence margin) are applied locally.
   - High-security zones (`server_room_high_security`) automatically lock down and deny offline biometric-only access.
3. **Emergency Fallback Verification**:
   - Authorized personnel can trigger offline step-up verification via time-based one-time passcodes (TOTP, RFC 6238) synchronized to internal hardware clocks.
4. **Privacy-Preserving Minimal Local Storage**:
   - Kiosks **NEVER** store raw biometric face photos or raw feature embeddings in offline event queues.
   - Events store only `{event_id, timestamp, user_pseudonym_hash, zone_id, decision, reason, hmac_signature}`.
   - Append-only tamper-evident cryptographic hash chain ($H_i = \text{SHA256}(H_{i-1} \parallel \text{Event}_i)$).
5. **Reconnection & Synchronization**:
   - Upon network restoration, queued events are batch-transmitted to `/sync/offline-logs`.
   - The central backend validates signatures, detects replay anomalies, updates audit databases, and returns an authenticated synchronization receipt.

---

## 4. Performance & Evaluation Benchmarks

- **Decision Time**: Target $\le 500\text{ ms}$ backend compute; $\le 1.2\text{ s}$ total kiosk turnaround (well within the $\le 2.0\text{ s}$ requirement).
- **APCER** (Attack Presentation Classification Error Rate): $\le 2.5\%$.
- **BPCER** (Bona Fide Presentation Classification Error Rate): $\le 1.8\%$.
- **FAR** (False Acceptance Rate): $\le 0.1\%$.
- **FRR** (False Rejection Rate): $\le 2.0\%$.
