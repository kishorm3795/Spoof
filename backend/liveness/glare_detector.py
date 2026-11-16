"""
backend/liveness/glare_detector.py
----------------------------------
Specular reflection and chromaticity distribution analyzer for screen replay attack detection.
Screens (smartphones, tablets, computer monitors) exhibit:
1. Glass surface specular highlights and harsh illumination reflections.
2. Backlight RGB color imbalances (abnormal blue-channel spectral bias).
3. Localized luminance clipping in digital displays compared to diffuse organic skin.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from config import GLARE_SPECULAR_MAX_RATIO


class GlareDetector:
    """
    Detects screen replay presentations by analyzing specular reflections,
    glass glare hotspots, and LCD/OLED spectral color temperature signatures.
    """

    def __init__(self, max_specular_ratio: float = GLARE_SPECULAR_MAX_RATIO):
        self.max_specular_ratio = max_specular_ratio

    def analyze(self, image: Image.Image | np.ndarray) -> dict:
        """
        Inspects the image for screen reflection artifacts and chromatic bias.

        Returns:
            dict containing:
                score (float 0.0-1.0): 1.0 = genuine diffuse skin, 0.0 = screen replay
                specular_ratio (float): Fraction of pixels showing clipped specular reflection
                blue_bias (float): Ratio of blue channel to red channel energy
                is_anomaly (bool): True if screen replay signature is detected
                indicators (list[str]): Diagnostic findings
        """
        if isinstance(image, Image.Image):
            rgb = np.array(image.convert("RGB"), dtype=np.float32)
        else:
            if image.ndim == 2:
                # Monochromatic input: duplicate across 3 channels
                rgb = np.stack([image, image, image], axis=-1).astype(np.float32)
            else:
                rgb = image.astype(np.float32)

        h, w, c = rgb.shape
        total_pixels = h * w
        if total_pixels == 0:
            return {
                "score": 0.5,
                "specular_ratio": 0.0,
                "blue_bias": 1.0,
                "is_anomaly": False,
                "indicators": ["Empty image"],
            }

        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        luminance = 0.299 * r + 0.587 * g + 0.114 * b

        # 1. Specular highlight detection: pixels saturated in all channels (> 245)
        specular_mask = (r > 245.0) & (g > 245.0) & (b > 245.0)
        specular_pixels = int(np.sum(specular_mask))
        specular_ratio = specular_pixels / float(total_pixels)

        # 2. Chromatic blue bias detection
        # Natural human skin under typical ambient indoor lighting has R > B and R > G.
        # Electronic screens emit concentrated blue phosphor / LED peaks.
        mean_r = float(np.mean(r)) + 1e-4
        mean_g = float(np.mean(g)) + 1e-4
        mean_b = float(np.mean(b)) + 1e-4

        blue_bias = mean_b / mean_r
        rg_ratio  = mean_r / mean_g

        # 3. Dynamic range clipping: pixels at luminance ceiling (> 250)
        clipped_high = float(np.sum(luminance >= 252.0)) / float(total_pixels)

        indicators = []
        is_anomaly = False

        # Evaluate specular reflections
        if specular_ratio > self.max_specular_ratio:
            is_anomaly = True
            indicators.append(
                f"High specular reflection ({specular_ratio:.3%}) typical of screen glass glare"
            )
            score_glare = max(0.1, 1.0 - (specular_ratio / self.max_specular_ratio) * 0.8)
        else:
            score_glare = 1.0 - (specular_ratio / self.max_specular_ratio) * 0.3

        # Evaluate chromatic temperature
        # Normal skin blue_bias is typically 0.55 - 0.95. Screen replays often exceed 1.05.
        if blue_bias > 1.10:
            is_anomaly = True
            indicators.append(
                f"Elevated blue spectral bias ({blue_bias:.2f}) indicates digital backlight"
            )
            score_color = max(0.15, 1.0 - (blue_bias - 1.10) * 1.5)
        elif blue_bias < 0.40:
            # Harsh monochromatic or paper filter
            indicators.append(f"Unusually low blue channel balance ({blue_bias:.2f})")
            score_color = 0.5
        else:
            score_color = 0.95

        # Evaluate highlight blowout
        if clipped_high > 0.05:
            indicators.append(f"Excessive luminance saturation ({clipped_high:.2%})")
            score_clip = max(0.2, 1.0 - clipped_high * 4.0)
        else:
            score_clip = 1.0

        final_score = float(np.clip(
            0.45 * score_glare + 0.35 * score_color + 0.20 * score_clip,
            0.05,
            0.98,
        ))

        return {
            "score": round(final_score, 4),
            "specular_ratio": round(specular_ratio, 4),
            "blue_bias": round(blue_bias, 3),
            "is_anomaly": is_anomaly,
            "indicators": indicators,
        }
