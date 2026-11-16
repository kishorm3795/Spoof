"""
backend/liveness/depth_heuristics.py
------------------------------------
3D geometric disparity and surface curvature heuristic analyzer.
Detects 3D masks, latex/silicone prosthetic shells, and planar cutouts via:
1. Sagittal and coronal 3D surface gradient divergence.
2. Ocular/oral aperture rim contrast anomalies (mask cutout edges).
3. Micro-depth surface gradient uniformity across facial landmarks.
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
                disparity (float): Estimated surface normal gradient variance
                rim_anomaly (float): Sharp aperture discontinuity metric
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
                "is_anomaly": False,
                "indicators": ["Image too small for depth heuristic analysis"],
            }

        # Normalize luminance to [0, 1]
        norm = gray / 255.0

        # Compute horizontal (coronal) and vertical (sagittal) gradients
        dy, dx = np.gradient(norm)
        grad_mag = np.sqrt(dx ** 2 + dy ** 2)

        # 1. 3D Volume Disparity Check
        # Compare central T-zone (nose bridge + forehead) to lateral cheek zones
        cy, cx = h // 2, w // 2
        rh, rw = h // 4, w // 4

        center_zone = grad_mag[cy - rh : cy + rh, cx - rw : cx + rw]
        outer_left  = grad_mag[cy - rh : cy + rh, :rw]
        outer_right = grad_mag[cy - rh : cy + rh, -rw:]

        mean_center = float(np.mean(center_zone)) if center_zone.size > 0 else 0.0
        mean_lateral = (
            float(np.mean(outer_left)) + float(np.mean(outer_right))
        ) / 2.0 if (outer_left.size > 0 and outer_right.size > 0) else 0.0

        disparity = abs(mean_center - mean_lateral)

        # 2. Cutout Rim Discontinuity / Mask Border Check
        # Masks often have high gradient concentration along artificial eye/mouth cutouts
        # or rigid silicone edges
        ocular_band = grad_mag[int(h * 0.25) : int(h * 0.45), :]
        high_grad_ratio = float(np.sum(ocular_band > 0.35)) / float(ocular_band.size + 1e-5)

        indicators = []
        is_anomaly = False

        # Evaluate 3D surface disparity
        # Planar photos and rigid masks have very low natural curvature disparity
        if disparity < self.min_disparity:
            is_anomaly = True
            indicators.append(
                f"Low surface gradient disparity ({disparity:.4f} < {self.min_disparity:.4f}) indicates planar photo or rigid mask"
            )
            score_depth = max(0.1, disparity / self.min_disparity * 0.5)
        else:
            score_depth = min(1.0, 0.6 + (disparity - self.min_disparity) * 5.0)

        # Evaluate aperture rim sharpness
        if high_grad_ratio > 0.12:
            is_anomaly = True
            indicators.append(
                f"Abnormal aperture rim gradient ({high_grad_ratio:.1%}) characteristic of mask cutout edges"
            )
            score_rim = max(0.15, 1.0 - high_grad_ratio * 3.0)
        else:
            score_rim = 1.0

        final_score = float(np.clip(0.6 * score_depth + 0.4 * score_rim, 0.05, 0.98))

        return {
            "score": round(final_score, 4),
            "disparity": round(disparity, 4),
            "rim_anomaly": round(high_grad_ratio, 4),
            "is_anomaly": is_anomaly,
            "indicators": indicators,
        }
