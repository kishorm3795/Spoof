"""
tests/test_liveness.py
----------------------
Unit and integration tests for passive anti-spoofing algorithms:
- FrequencyAnalyzer
- GlareDetector
- MoireDetector
- DepthHeuristics
- LivenessEngine
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
import pytest

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from liveness.frequency_analyzer import FrequencyAnalyzer
from liveness.glare_detector import GlareDetector
from liveness.moire_detector import MoireDetector
from liveness.depth_heuristics import DepthHeuristics
from liveness.engine import LivenessEngine


def create_synthetic_live_face() -> Image.Image:
    """Generates a synthetic face with organic skin gradients and natural texture."""
    arr = np.zeros((120, 120, 3), dtype=np.uint8)
    # Warm skin tone base (R > G > B)
    arr[:, :, 0] = 195  # Red
    arr[:, :, 1] = 145  # Green
    arr[:, :, 2] = 115  # Blue

    # Add 3D facial curvature gradient (brighter nose/forehead, darker cheeks)
    y, x = np.ogrid[:120, :120]
    dist = np.sqrt((x - 60) ** 2 + (y - 60) ** 2)
    curvature = np.clip(30 - dist * 0.45, -20, 30).astype(np.int16)
    for c in range(3):
        arr[:, :, c] = np.clip(arr[:, :, c].astype(np.int16) + curvature, 0, 255).astype(np.uint8)

    # Add micro-skin texture
    rng = np.random.default_rng(42)
    smooth_noise = gaussian_filter(rng.normal(0, 15, (120, 120, 3)), sigma=1.0).astype(np.int16)
    arr = np.clip(arr.astype(np.int16) + smooth_noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def create_synthetic_printed_photo() -> Image.Image:
    """Simulates a printed paper photo: smoothed low frequencies with paper blur."""
    live = np.array(create_synthetic_live_face(), dtype=np.float32)
    # Blur image to simulate ink absorption and print loss
    blurred = gaussian_filter(live, sigma=4.0)
    return Image.fromarray(np.clip(blurred, 0, 255).astype(np.uint8))


def create_synthetic_screen_replay() -> Image.Image:
    """Simulates a phone screen replay: harsh specular glare and blue backlight."""
    base = np.array(create_synthetic_live_face(), dtype=np.float32)
    # Strong blue channel emission
    base[:, :, 2] += 80.0
    base[:, :, 0] -= 25.0
    # Add specular glass reflection hot spot
    base[35:75, 40:80, :] = 255.0
    arr = np.clip(base, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def create_synthetic_moire_screen() -> Image.Image:
    """Simulates Moire pixel matrix aliasing via 2D sinusoidal grid."""
    base = np.array(create_synthetic_live_face(), dtype=np.float32)
    y, x = np.ogrid[:120, :120]
    moire_grid = (np.sin(x * 0.8) * np.cos(y * 0.8)) * 35.0
    for c in range(3):
        base[:, :, c] = np.clip(base[:, :, c] + moire_grid, 0, 255)
    return Image.fromarray(base.astype(np.uint8))


def create_synthetic_mask() -> Image.Image:
    """Simulates a flat/rigid paper or silicone mask with sharp cutout rims."""
    arr = np.full((120, 120, 3), 160, dtype=np.uint8)
    # Flat planar surface (95%+ flat ratio)
    # Cutout eye apertures with sharp rim transitions
    arr[38:52, 28:50, :] = 20  # left eye hole
    arr[38:52, 70:92, :] = 20  # right eye hole
    arr[78:90, 42:78, :] = 20  # mouth hole
    return Image.fromarray(arr)


# ── Tests ─────────────────────────────────────────────────────────────────

def test_frequency_analyzer_live_vs_printed():
    analyzer = FrequencyAnalyzer()
    live_res = analyzer.analyze(create_synthetic_live_face())
    print_res = analyzer.analyze(create_synthetic_printed_photo())

    assert live_res["score"] > print_res["score"], "Live skin should score higher than printed photo in frequency"
    assert print_res["is_anomaly"] is True, "Printed photo should be flagged as anomaly"
    assert "high_low_ratio" in live_res
    assert "laplacian_var" in live_res


def test_glare_detector_live_vs_screen():
    detector = GlareDetector()
    live_res = detector.analyze(create_synthetic_live_face())
    screen_res = detector.analyze(create_synthetic_screen_replay())

    assert live_res["score"] > screen_res["score"], "Live skin should score higher than screen replay with glare"
    assert screen_res["specular_ratio"] > 0.02, "Screen replay should have detectable specular ratio"
    assert screen_res["blue_bias"] > 1.0, "Screen replay should have elevated blue spectral bias"


def test_moire_detector_pattern():
    detector = MoireDetector()
    live_res = detector.analyze(create_synthetic_live_face())
    moire_res = detector.analyze(create_synthetic_moire_screen())

    assert moire_res["peak_ratio"] > live_res["peak_ratio"], "Moire pattern should produce harmonic frequency peak"


def test_depth_heuristics_mask():
    heuristics = DepthHeuristics()
    live_res = heuristics.analyze(create_synthetic_live_face())
    mask_res = heuristics.analyze(create_synthetic_mask())

    assert live_res["score"] > mask_res["score"], "Live 3D curved face should score higher than flat cutout mask"
    assert mask_res["is_anomaly"] is True, "Mask should be flagged as anomaly"


def test_liveness_engine_e2e_sla():
    engine = LivenessEngine()
    live_img = create_synthetic_live_face()
    res = engine.evaluate(live_img)

    assert "is_live" in res
    assert "liveness_score" in res
    assert "decision_outcome" in res
    assert "latency_ms" in res
    assert res["within_sla"] is True, "Must complete decision in under 2.0 seconds"
    assert res["latency_ms"] < 2000.0


def test_liveness_engine_spoof_classifications():
    engine = LivenessEngine()

    # Printed photo attack
    p_res = engine.evaluate(create_synthetic_printed_photo())
    assert p_res["decision_outcome"] in ["DENY", "REQUEST VERIFICATION"]

    # Screen glare attack
    s_res = engine.evaluate(create_synthetic_screen_replay())
    assert s_res["decision_outcome"] in ["DENY", "REQUEST VERIFICATION"]
    assert s_res["spoof_type"] == "screen_replay"

    # Mask attack
    m_res = engine.evaluate(create_synthetic_mask())
    assert m_res["decision_outcome"] in ["DENY", "REQUEST VERIFICATION"]
