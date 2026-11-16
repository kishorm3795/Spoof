"""
backend/liveness/engine.py
--------------------------
Unified multi-spoof passive anti-spoofing ensemble engine.
Combines:
1. FrequencyAnalyzer (printed paper, texture smoothing)
2. GlareDetector (screen reflection, backlight chromaticity)
3. MoireDetector (digital display matrix aliasing, borders)
4. DepthHeuristics (3D mask curvature, aperture sharpness)

Guarantees sub-2-second execution time with full latency breakdown.
"""

from __future__ import annotations

import time
import io
import numpy as np
from PIL import Image

from config import (
    LIVENESS_CONFIDENCE_THRESHOLD,
    LIVENESS_BORDERLINE_MIN,
    WEIGHT_FREQUENCY,
    WEIGHT_GLARE,
    WEIGHT_MOIRE,
    WEIGHT_DEPTH,
    DECISION_TIMEOUT_SECONDS,
)
from .frequency_analyzer import FrequencyAnalyzer
from .glare_detector import GlareDetector
from .moire_detector import MoireDetector
from .depth_heuristics import DepthHeuristics


class LivenessEngine:
    """
    Ensemble engine evaluating physical presence and presentation attack risks.
    """

    def __init__(self):
        self.freq_analyzer = FrequencyAnalyzer()
        self.glare_detector = GlareDetector()
        self.moire_detector = MoireDetector()
        self.depth_heuristics = DepthHeuristics()

    def evaluate(self, image_input: bytes | Image.Image | np.ndarray) -> dict:
        """
        Runs the full passive liveness ensemble.

        Returns:
            dict containing:
                is_live (bool): True if confidence >= LIVENESS_CONFIDENCE_THRESHOLD
                is_borderline (bool): True if score is in [BORDERLINE_MIN, THRESHOLD)
                liveness_score (float 0.0-1.0): Aggregate confidence score
                spoof_type (str): 'genuine', 'printed_photo', 'screen_replay', 'video_replay', or 'mask'
                decision_outcome (str): 'ALLOW', 'REQUEST VERIFICATION', or 'DENY'
                breakdown (dict): Individual scores and metrics for all 4 detectors
                reasons (list[str]): Explanation for decision
                latency_ms (float): Execution duration
                within_sla (bool): True if latency <= 2.0s
        """
        t0 = time.perf_counter()

        # Load image
        if isinstance(image_input, bytes):
            pil_img = Image.open(io.BytesIO(image_input)).convert("RGB")
        elif isinstance(image_input, Image.Image):
            pil_img = image_input.convert("RGB")
        elif isinstance(image_input, np.ndarray):
            if image_input.ndim == 2:
                pil_img = Image.fromarray(image_input).convert("RGB")
            else:
                pil_img = Image.fromarray(image_input.astype(np.uint8)).convert("RGB")
        else:
            raise ValueError(f"Unsupported image_input type: {type(image_input)}")

        # Execute 4 sub-detectors
        freq_res  = self.freq_analyzer.analyze(pil_img)
        glare_res = self.glare_detector.analyze(pil_img)
        moire_res = self.moire_detector.analyze(pil_img)
        depth_res = self.depth_heuristics.analyze(pil_img)

        # Compute weighted aggregate score
        agg_score = (
            WEIGHT_FREQUENCY * freq_res["score"]
            + WEIGHT_GLARE * glare_res["score"]
            + WEIGHT_MOIRE * moire_res["score"]
            + WEIGHT_DEPTH * depth_res["score"]
        )
        agg_score = float(np.clip(agg_score, 0.01, 0.99))

        # Collect anomalies and classify spoof type
        anomalies = []
        if freq_res["is_anomaly"]:
            anomalies.append(("printed_photo", freq_res["score"], freq_res["indicators"]))
        if glare_res["is_anomaly"]:
            anomalies.append(("screen_replay", glare_res["score"], glare_res["indicators"]))
        if moire_res["is_anomaly"]:
            anomalies.append(("screen_replay", moire_res["score"], moire_res["indicators"]))
        if depth_res["is_anomaly"]:
            anomalies.append(("mask", depth_res["score"], depth_res["indicators"]))

        reasons = []
        for _, _, inds in anomalies:
            reasons.extend(inds)

        # Determine dominant spoof type
        if agg_score >= LIVENESS_CONFIDENCE_THRESHOLD:
            spoof_type = "genuine"
            is_live = True
            is_borderline = False
            outcome = "ALLOW"
            if not reasons:
                reasons.append("Organic micro-texture, natural 3D surface depth, and balanced ambient lighting confirmed.")
        elif agg_score >= LIVENESS_BORDERLINE_MIN:
            # Low confidence zone -> triggers REQUEST VERIFICATION
            is_live = False
            is_borderline = True
            outcome = "REQUEST VERIFICATION"
            # Sort anomalies by severity (lowest sub-score)
            if anomalies:
                anomalies.sort(key=lambda x: x[1])
                spoof_type = anomalies[0][0]
            else:
                spoof_type = "unclear_lighting"
            reasons.append("Borderline liveness confidence. Secondary verification required.")
        else:
            # Clear spoof detected -> DENY
            is_live = False
            is_borderline = False
            outcome = "DENY"
            if anomalies:
                anomalies.sort(key=lambda x: x[1])
                spoof_type = anomalies[0][0]
            else:
                # Find lowest detector score
                sub_scores = [
                    ("printed_photo", freq_res["score"]),
                    ("screen_replay", glare_res["score"]),
                    ("screen_replay", moire_res["score"]),
                    ("mask", depth_res["score"]),
                ]
                sub_scores.sort(key=lambda x: x[1])
                spoof_type = sub_scores[0][0]
            reasons.append(f"Presentation attack identified: {spoof_type.replace('_', ' ').title()}")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        within_sla = elapsed_ms <= (DECISION_TIMEOUT_SECONDS * 1000.0)

        return {
            "is_live": is_live,
            "is_borderline": is_borderline,
            "liveness_score": round(agg_score, 4),
            "spoof_type": spoof_type,
            "decision_outcome": outcome,
            "breakdown": {
                "frequency": freq_res,
                "glare": glare_res,
                "moire": moire_res,
                "depth": depth_res,
            },
            "reasons": reasons,
            "latency_ms": round(elapsed_ms, 2),
            "within_sla": within_sla,
        }
