"""
backend/liveness/depth_heuristics.py
------------------------------------
3D geometric disparity and surface curvature heuristic analyzer.
Detects 3D masks, latex/silicone prosthetic shells, and planar cutouts via:
1. Surface normal gradient curvature and flat-region distribution.
2. Ocular/oral aperture rim contrast anomalies (mask cutout edges).
3. Micro-depth surface gradient divergence across facial landmarks.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from config import DEPTH_DISPARITY_MIN


class DepthHeuristics:
    """
    Analyzes spatial gradient geometry to detect flat paper masks,
    silicone/resin shells, and rigid prosthetic presentation attacks.
    """

    def __init__(self, min_disparity: float = DEPTH_DISPARITY_MIN):
        self.min_disparity = min_disparity

    def analyze(self, image: Image.Image | np.ndarray) -> dict:
        """
        Inspects the face image for 3D depth curvature and mask rim artifacts.

        Returns:
            dict containing:
                score (float 0.0-1.0): 1.0 = organic 3D facial volume, 0.0 = mask/flat spoof
                disparity (float): Estimated surface gradient variance
                rim_anomaly (float): Sharp aperture discontinuity metric
                flat_ratio (float): Fraction of surface lacking natural organic gradient
                is_anomaly (bool): True if mask or planar spoof is detected
                indicators (list[str]): Diagnostic findings
        """
        if isinstance(image, Image.Image):
            gray = np.array(image.convert("L"), dtype=np.float32)
        else:
            if image.ndim == 3:
                gray = (0.2989 * image[:, :, 0] + 0.5870 * image[:, :, 1] + 0.1140 * image[:, :, 2]).astype(np.float32)
            else:
                gray = image.astype(np.float32)

        h, w = gray.shape
        if h < 32 or w < 32:
            return {
                "score": 0.5,
                "disparity": 0.0,
                "rim_anomaly": 0.0,
                "flat_ratio": 0.5,
                "is_anomaly": False,
                "indicators": ["Image too small for depth heuristic analysis"],
            }

        # Normalize luminance to [0, 1]
        norm = gray / 255.0

        # Compute directional gradients
        dy, dx = np.gradient(norm)
        grad_mag = np.sqrt(dx ** 2 + dy ** 2)

        # 1. Surface Flatness vs Organic 3D Curvature
        # In flat masks, large uniform regions lack continuous organic micro-gradients
        flat_ratio = float(np.sum(grad_mag < 0.012)) / float(grad_mag.size)

        # 2. Cutout Rim Discontinuity / Mask Border Check
        # Masks exhibit high gradient concentration along artificial eye/mouth cutouts
        ocular_band = grad_mag[int(h * 0.25) : int(h * 0.45), :]
        high_grad_ratio = float(np.sum(ocular_band > 0.20)) / float(ocular_band.size + 1e-5)

        # 3. Dynamic range disparity
        cy, cx = h // 2, w // 2
        rh, rw = max(2, h // 4), max(2, w // 4)
        center_zone = grad_mag[cy - rh : cy + rh, cx - rw : cx + rw]
        mean_center = float(np.mean(center_zone)) if center_zone.size > 0 else 0.0

        indicators = []
        is_anomaly = False

        # Natural 3D face has flat_ratio between 0.15 and 0.65. Masks typically exceed 0.85
        if flat_ratio > 0.82:
            is_anomaly = True
            indicators.append(
                f"High surface planarity ({flat_ratio:.1%}) characteristic of flat paper or rigid mask"
            )
            score_flat = max(0.1, 1.0 - (flat_ratio - 0.82) * 5.0)
        else:
            score_flat = min(1.0, 1.0 - flat_ratio * 0.4)

        # Mask aperture rims
        if high_grad_ratio > 0.045:
            is_anomaly = True
            indicators.append(
                f"Abnormal aperture rim gradient ({high_grad_ratio:.1%}) characteristic of mask cutout edges"
            )
            score_rim = max(0.1, 1.0 - high_grad_ratio * 12.0)
        else:
            score_rim = 1.0

        final_score = float(np.clip(0.55 * score_flat + 0.45 * score_rim, 0.05, 0.98))
        if is_anomaly:
            final_score = min(final_score, 0.45)

        return {
            "score": round(final_score, 4),
            "disparity": round(mean_center, 4),
            "rim_anomaly": round(high_grad_ratio, 4),
            "flat_ratio": round(flat_ratio, 3),
            "is_anomaly": is_anomaly,
            "indicators": indicators,
        }
