"""
backend/liveness/frequency_analyzer.py
--------------------------------------
Frequency-domain texture and spatial energy analyzer for passive anti-spoofing.
Detects printed paper photographs and texture-smoothed spoofs via:
1. 2D Fast Fourier Transform (FFT) radial power distribution.
2. High-to-low spatial frequency energy ratio.
3. Laplacian micro-texture variance and blur-boundary metrics.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from config import FREQ_HIGH_LOW_RATIO_MIN


class FrequencyAnalyzer:
    """
    Analyzes frequency spectrum of face images to distinguish genuine 3D skin
    from printed paper textures and low-frequency printed presentations.
    """

    def __init__(self, min_ratio: float = FREQ_HIGH_LOW_RATIO_MIN):
        self.min_ratio = min_ratio

    def analyze(self, image: Image.Image | np.ndarray) -> dict:
        """
        Inspects the image in the frequency domain.

        Returns:
            dict containing:
                score (float 0.0-1.0): 1.0 = genuine skin texture, 0.0 = printed paper artifact
                high_low_ratio (float): Ratio of high to low frequency energy
                laplacian_var (float): Texture sharpness metric
                is_anomaly (bool): True if photo print / blur anomaly detected
                indicators (list[str]): Diagnostic findings
        """
        if isinstance(image, Image.Image):
            gray = np.array(image.convert("L"), dtype=np.float32)
        else:
            if image.ndim == 3:
                # RGB to Gray using standard luminance weights
                gray = (0.2989 * image[:, :, 0] + 0.5870 * image[:, :, 1] + 0.1140 * image[:, :, 2]).astype(np.float32)
            else:
                gray = image.astype(np.float32)

        h, w = gray.shape
        if h < 16 or w < 16:
            return {
                "score": 0.5,
                "high_low_ratio": 0.0,
                "laplacian_var": 0.0,
                "is_anomaly": False,
                "indicators": ["Image dimensions too small for reliable FFT analysis"],
            }

        # 1. 2D FFT and Centering
        f = np.fft.fft2(gray)
        fshift = np.fft.fftshift(f)
        magnitude = np.abs(fshift)

        cy, cx = h // 2, w // 2
        y, x = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

        r_low = min(h, w) * 0.15
        r_high = min(h, w) * 0.45

        low_mask = dist_from_center <= r_low
        high_mask = (dist_from_center > r_low) & (dist_from_center <= r_high)

        low_energy = float(np.sum(magnitude[low_mask]))
        high_energy = float(np.sum(magnitude[high_mask]))

        high_low_ratio = high_energy / (low_energy + 1e-6)

        # 2. Discrete Laplacian variance for micro-texture gradient
        kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        # 2D correlation via frequency domain or simple spatial convolution
        pad_gray = np.pad(gray, 1, mode="reflect")
        laplacian = (
            pad_gray[:-2, 1:-1]
            + pad_gray[2:, 1:-1]
            + pad_gray[1:-1, :-2]
            + pad_gray[1:-1, 2:]
            - 4 * pad_gray[1:-1, 1:-1]
        )
        lap_var = float(np.var(laplacian))

        # 3. Scoring
        indicators = []
        is_anomaly = False

        # Live human skin typically has balanced high-low ratio (0.07 to 0.35)
        # Printed photos often suffer from high-frequency attenuation (< 0.05) or paper noise spikes (> 0.45)
        if high_low_ratio < self.min_ratio:
            is_anomaly = True
            indicators.append(f"Low high-frequency energy ({high_low_ratio:.4f} < {self.min_ratio:.4f}) indicates printed photo or blur")
            score_ratio = max(0.1, high_low_ratio / self.min_ratio * 0.5)
        elif high_low_ratio > 0.48:
            is_anomaly = True
            indicators.append(f"Abnormally high spatial frequency ({high_low_ratio:.4f}) indicates paper halftone/dot-matrix pattern")
            score_ratio = 0.35
        else:
            score_ratio = min(1.0, 0.6 + (high_low_ratio - self.min_ratio) * 1.5)

        # Micro-texture sharpness: < 40 indicates washed-out printed paper / over-smoothed spoof
        if lap_var < 45.0:
            indicators.append(f"Low micro-texture variance ({lap_var:.1f})")
            score_texture = max(0.15, lap_var / 45.0 * 0.5)
        else:
            score_texture = min(1.0, 0.5 + (lap_var - 45.0) / 200.0)

        final_score = float(np.clip(0.6 * score_ratio + 0.4 * score_texture, 0.05, 0.98))

        return {
            "score": round(final_score, 4),
            "high_low_ratio": round(high_low_ratio, 4),
            "laplacian_var": round(lap_var, 2),
            "is_anomaly": is_anomaly,
            "indicators": indicators,
        }
