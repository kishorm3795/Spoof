"""
backend/liveness/moire_detector.py
----------------------------------
Moire pattern interference and rectangular boundary edge detector.
Target attack vectors:
1. Screen pixel grid aliasing creating distinct 2D periodic Moire frequency peaks.
2. Printed paper and smartphone bezel high-contrast boundary line artifacts.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from config import MOIRE_BANDING_PEAK_MAX


class MoireDetector:
    """
    Detects periodic spatial interference (Moire patterns) caused by camera sensor
    interaction with electronic display matrices, and detects bezel/paper borders.
    """

    def __init__(self, max_peak_ratio: float = MOIRE_BANDING_PEAK_MAX):
        self.max_peak_ratio = max_peak_ratio

    def analyze(self, image: Image.Image | np.ndarray) -> dict:
        """
        Inspects the image for Moire periodic patterns and perimeter borders.

        Returns:
            dict containing:
                score (float 0.0-1.0): 1.0 = genuine live face, 0.0 = screen/print artifact
                peak_ratio (float): Ratio of maximum harmonic peak to average spectrum
                border_strength (float): Peripheral collinear edge gradient magnitude
                is_anomaly (bool): True if Moire or border artifact is detected
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
                "peak_ratio": 0.0,
                "border_strength": 0.0,
                "is_anomaly": False,
                "indicators": ["Image too small for Moire pattern analysis"],
            }

        # 1. Fourier 2D Harmonic Peak Analysis for Moire Detection
        f = np.fft.fft2(gray)
        fshift = np.fft.fftshift(f)
        magnitude = np.abs(fshift)

        cy, cx = h // 2, w // 2
        y, x = np.ogrid[:h, :w]
        dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

        # Exclude DC component and immediate low frequencies (radius <= 4)
        # and extreme nyquist corners
        valid_zone = (dist > 5) & (dist < min(h, w) * 0.45)
        if np.any(valid_zone):
            mid_mags = magnitude[valid_zone]
            mean_mag = float(np.mean(mid_mags)) + 1e-5
            max_mag = float(np.max(mid_mags))
            peak_ratio = (max_mag - mean_mag) / (mean_mag * 12.0)
        else:
            peak_ratio = 0.0

        # 2. Peripheral Bezel / Photo Edge Gradient Detection
        # Check outer 12% margins for strong horizontal/vertical continuous edges
        margin_y = max(2, int(h * 0.12))
        margin_x = max(2, int(w * 0.12))

        # Sobel gradients
        gy = np.abs(np.diff(gray, axis=0))
        gx = np.abs(np.diff(gray, axis=1))

        top_edge    = float(np.mean(gy[:margin_y, :]))
        bottom_edge = float(np.mean(gy[-margin_y:, :]))
        left_edge   = float(np.mean(gx[:, :margin_x]))
        right_edge  = float(np.mean(gx[:, -margin_x:]))

        center_grad = (
            float(np.mean(gy[margin_y:-margin_y, margin_x:-margin_x]))
            + float(np.mean(gx[margin_y:-margin_y, margin_x:-margin_x]))
        ) / 2.0 + 1e-5

        max_perimeter_edge = max(top_edge, bottom_edge, left_edge, right_edge)
        border_strength = max_perimeter_edge / center_grad

        indicators = []
        is_anomaly = False

        # Evaluate Moire peak
        if peak_ratio > self.max_peak_ratio:
            is_anomaly = True
            indicators.append(
                f"Harmonic Moire interference detected (peak ratio: {peak_ratio:.3f} > {self.max_peak_ratio:.3f})"
            )
            score_moire = max(0.1, 1.0 - (peak_ratio / self.max_peak_ratio) * 0.75)
        else:
            score_moire = 1.0 - (peak_ratio / self.max_peak_ratio) * 0.25

        # Evaluate Border Strength (ratio > 2.2 indicates paper/screen frame)
        if border_strength > 2.2:
            is_anomaly = True
            indicators.append(
                f"High-contrast peripheral border edge ({border_strength:.2f}x center) indicates device bezel or paper cutoff"
            )
            score_border = max(0.15, 1.0 - (border_strength - 2.2) * 0.4)
        else:
            score_border = 1.0

        final_score = float(np.clip(0.6 * score_moire + 0.4 * score_border, 0.05, 0.98))

        return {
            "score": round(final_score, 4),
            "peak_ratio": round(peak_ratio, 4),
            "border_strength": round(border_strength, 3),
            "is_anomaly": is_anomaly,
            "indicators": indicators,
        }
