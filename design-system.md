# HID Smart Kiosk Design System

**Art Direction**: Precision Enterprise Glassmorphism & Security HUD
**Domain**: Physical Access Control & Biometric Entry Telemetry

---

## 1. Color Palette (60-30-10 Distribution)

### 60% — Dominant Canvas & Background
- **Deep Space Obsidian**: `#070c18` (Primary viewport canvas)
- **Sub-surface Elevation**: `#0b1325` (Card foundations)
- **Background Gradient**: `radial-gradient(ellipse at 50% 0%, #11203d 0%, #070c18 70%)`

### 30% — Structural Surface & Glassmorphism
- **Glass Panel Surface**: `rgba(13, 23, 42, 0.78)`
- **Glass Specular Border**: `1px solid rgba(255, 255, 255, 0.12)`
- **Active Focused Border**: `1px solid rgba(0, 194, 255, 0.5)`
- **Backdrop Blur**: `blur(18px) saturate(160%)`
- **Text Primary**: `#f8fafc` (High contrast crisp white)
- **Text Secondary / Muted**: `#94a3b8` (Slate telemetry text)
- **Text Dim**: `#64748b` (Labels and metadata)

### 10% — Telemetry Accents & State Indicators
- **HID Brand Cobalt**: `#0066cc` (`rgba(0, 102, 204, 1.0)`)
- **Electric Cyan Glow**: `#00c2ff` (`rgba(0, 194, 255, 0.35)`)
- **Verdict ALLOW (Emerald)**: `#10b981` (Glow: `rgba(16, 185, 129, 0.35)`)
- **Verdict STEP-UP / VERIFY (Amber)**: `#f59e0b` (Glow: `rgba(245, 158, 11, 0.35)`)
- **Verdict DENY (Threat Crimson)**: `#ef4444` (Glow: `rgba(239, 68, 68, 0.35)`)

---

## 2. Typography Scale

- **Font Family**: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
- **Monospace Telemetry**: "JetBrains Mono", "Fira Code", monospace (latency timers, event hashes, OTPs)
- **Scale**:
  - `Display / Banner`: 32px / 2rem, 800 weight, letter-spacing -0.02em
  - `H1 / Section Header`: 22px / 1.375rem, 700 weight, letter-spacing -0.01em
  - `H2 / Card Header`: 16px / 1.0rem, 600 weight
  - `Body / Standard`: 14px / 0.875rem, 400 weight, line-height 1.5
  - `Caption / Metric Label`: 11px / 0.6875rem, 600 weight, uppercase, letter-spacing 0.06em
  - `HUD Latency Counter`: 28px / 1.75rem, 800 weight, tabular-nums monospace

---

## 3. Elevation, Radius & Borders

- **Border Radius**:
  - Container / Outer Card: `18px` (`1.125rem`)
  - Video Feed / HUD Canvas: `14px` (`0.875rem`)
  - Badges / Pill Chips: `9999px` (Full capsule)
  - Buttons / Controls: `10px` (`0.625rem`)
  - Modals / Popups: `20px` (`1.25rem`)
- **Shadows**:
  - Glass Ambient: `0 16px 40px rgba(0, 0, 0, 0.45)`
  - Active Glow Allow: `0 0 25px rgba(16, 185, 129, 0.3)`
  - Active Glow Verify: `0 0 25px rgba(245, 158, 11, 0.3)`
  - Active Glow Deny: `0 0 25px rgba(239, 68, 68, 0.3)`

---

## 4. Component Architecture & Interactive States

- **HUD Video Frame**: Features corner bracket reticles (`border-top-left-radius`, etc.) that transition color dynamically from Cyan (scanning) to Green (Allow), Amber (Step-Up), or Red (Deny).
- **Sub-2.0s Stopwatch Timer**: Live ticking millisecond counter with green pill when $\le 2000\text{ms}$.
- **Campus Schedule Interactive Bar**: Sliders for time-of-day simulation, role toggle pills (`student`, `faculty`, `visitor`, etc.), and facility zone selectors.
- **Air-Gapped Offline Mode Switch**: Toggle that transitions interface into high-security offline mode with local audit queue counter and "Sync Decisions" reconciliation button.
- **No Emojis**: Strictly pure SVG vector paths and Lucide iconography for enterprise security grade finish.
