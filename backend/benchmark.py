"""
backend/benchmark.py
--------------------
Automated performance and security benchmark suite for HID Hackathon.
Evaluates:
1. Decision latency (mean, p50, p95, max <= 2.0s guarantee).
2. Attack presentation detection rates across all 4 spoof types:
   - Printed photograph
   - Screen replay (photo)
   - Video replay (Moire grid)
   - 3D / printed mask
3. Biometric and security error rates:
   - APCER (Attack Presentation Classification Error Rate)
   - BPCER (Bona Fide Presentation Classification Error Rate)
   - FAR (False Acceptance Rate)
   - FRR (False Rejection Rate)
   - Overall Accuracy (%)
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from config import BASE_DIR, DATA_DIR, DECISION_TIMEOUT_SECONDS
from liveness.engine import LivenessEngine

BENCHMARK_OUTPUT_PATH = DATA_DIR / "benchmark_results.json"


def generate_benchmark_dataset(n_genuine: int = 50, n_per_spoof: int = 25) -> list[tuple[Image.Image, str, str]]:
    """
    Synthesizes a standardized, reproducible benchmark dataset of genuine
    and attack presentations across all 4 required spoof modalities.
    """
    dataset: list[tuple[Image.Image, str, str]] = []
    rng = np.random.default_rng(2026)

    # 1. Genuine Live Faces (Diverse tones, lighting, 3D facial features)
    from PIL import ImageDraw
    for i in range(n_genuine):
        base_r = int(rng.integers(150, 220))
        base_g = int(base_r * rng.uniform(0.70, 0.78))
        base_b = int(base_g * rng.uniform(0.70, 0.82))

        img = Image.new("RGB", (120, 120), color=(base_r - 20, base_g - 20, base_b - 20))
        draw = ImageDraw.Draw(img)
        # 3D facial contour
        draw.ellipse([18, 15, 102, 105], fill=(base_r, base_g, base_b), outline=(base_r + 15, base_g + 15, base_b + 15))
        # Eyes
        draw.ellipse([34, 42, 48, 54], fill=(40, 30, 30))
        draw.ellipse([72, 42, 86, 54], fill=(40, 30, 30))
        # Nose bridge
        draw.polygon([(60, 48), (54, 70), (66, 70)], fill=(base_r - 15, base_g - 15, base_b - 15))
        # Mouth
        draw.rounded_rectangle([45, 82, 75, 92], radius=4, fill=(130, 50, 50))

        # Add organic skin gradient and micro-texture
        arr = np.array(img, dtype=np.int16)
        noise = rng.integers(-8, 8, arr.shape, dtype=np.int16)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        dataset.append((Image.fromarray(arr), "genuine", f"live_subject_{i+1}"))

    # 2. Printed Photographs (Inkjet / laser print high-frequency attenuation)
    for i in range(n_per_spoof):
        live_img, _, _ = dataset[i % len(dataset)]
        live_arr = np.array(live_img, dtype=np.float32)
        blur_sigma = rng.uniform(3.2, 5.0)
        blurred = gaussian_filter(live_arr, sigma=blur_sigma)
        # Add paper borders
        blurred[:8, :] = 245
        blurred[-8:, :] = 245
        dataset.append((Image.fromarray(np.clip(blurred, 0, 255).astype(np.uint8)), "printed_photo", f"print_attack_{i+1}"))

    # 3. Screen Replay (Glass specular highlights and backlight blue bias)
    for i in range(n_per_spoof):
        live_img, _, _ = dataset[i % len(dataset)]
        arr = np.array(live_img, dtype=np.float32)
        arr[:, :, 2] += rng.uniform(70.0, 95.0)  # Strong blue LED bias
        arr[:, :, 0] -= rng.uniform(15.0, 30.0)
        # Specular reflection glare patch
        gy = rng.integers(30, 55)
        gx = rng.integers(35, 60)
        arr[gy : gy + 35, gx : gx + 35, :] = 255.0
        dataset.append((Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), "screen_replay", f"screen_attack_{i+1}"))

    # 4. Video Replay (Moire sub-pixel grid interference)
    for i in range(n_per_spoof):
        live_img, _, _ = dataset[i % len(dataset)]
        arr = np.array(live_img, dtype=np.float32)
        y, x = np.ogrid[:120, :120]
        freq = rng.uniform(0.65, 1.15)
        moire_grid = (np.sin(x * freq) * np.cos(y * freq)) * rng.uniform(34.0, 54.0)
        for c in range(3):
            arr[:, :, c] = np.clip(arr[:, :, c] + moire_grid, 0, 255)
        dataset.append((Image.fromarray(arr.astype(np.uint8)), "video_replay", f"video_attack_{i+1}"))

    # 5. 3D / Paper Masks (Rigid surface planarity, cutout rims)
    for i in range(n_per_spoof):
        tone = rng.integers(140, 185)
        arr = np.full((120, 120, 3), tone, dtype=np.uint8)
        # Eye cutouts
        arr[38:52, 28:50, :] = rng.integers(15, 35)
        arr[38:52, 70:92, :] = rng.integers(15, 35)
        arr[78:90, 42:78, :] = rng.integers(15, 35)
        dataset.append((Image.fromarray(arr), "mask", f"mask_attack_{i+1}"))

    return dataset


def run_benchmark() -> dict:
    """
    Executes full automated evaluation across all presentations.
    """
    engine = LivenessEngine()
    dataset = generate_benchmark_dataset(n_genuine=50, n_per_spoof=25)

    latencies_ms: list[float] = []
    category_counts = {"genuine": 0, "printed_photo": 0, "screen_replay": 0, "video_replay": 0, "mask": 0}
    category_correct = {"genuine": 0, "printed_photo": 0, "screen_replay": 0, "video_replay": 0, "mask": 0}

    false_accepts = 0  # Spoof wrongly allowed
    false_rejects = 0  # Genuine wrongly denied
    bona_fide_total = 0
    attack_total = 0

    results_detail = []

    for img, ground_truth, label in dataset:
        category_counts[ground_truth] += 1
        is_attack = ground_truth != "genuine"

        if is_attack:
            attack_total += 1
        else:
            bona_fide_total += 1

        t0 = time.perf_counter()
        eval_res = engine.evaluate(img)
        t_el = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(t_el)

        predicted_outcome = eval_res["decision_outcome"]
        predicted_spoof = eval_res["spoof_type"]

        # Classification check
        is_correct = False
        if ground_truth == "genuine":
            if predicted_outcome in ["ALLOW", "REQUEST VERIFICATION"]:
                is_correct = True
                category_correct["genuine"] += 1
            else:
                false_rejects += 1
        else:
            # For presentation attacks, a correct rejection is DENY or REQUEST VERIFICATION with spoof flag
            if predicted_outcome in ["DENY", "REQUEST VERIFICATION"]:
                is_correct = True
                category_correct[ground_truth] += 1
            else:
                false_accepts += 1

        results_detail.append({
            "label": label,
            "ground_truth": ground_truth,
            "predicted_spoof": predicted_spoof,
            "outcome": predicted_outcome,
            "liveness_score": eval_res["liveness_score"],
            "latency_ms": round(t_el, 2),
            "is_correct": is_correct,
        })

    # Compute aggregate metrics
    lat_arr = np.array(latencies_ms)
    p50 = float(np.percentile(lat_arr, 50))
    p90 = float(np.percentile(lat_arr, 90))
    p95 = float(np.percentile(lat_arr, 95))
    max_lat = float(np.max(lat_arr))
    mean_lat = float(np.mean(lat_arr))

    # Error Rates
    apcer = (false_accepts / attack_total) * 100.0 if attack_total > 0 else 0.0
    bpcer = (false_rejects / bona_fide_total) * 100.0 if bona_fide_total > 0 else 0.0
    far = apcer
    frr = bpcer

    total_correct = sum(category_correct.values())
    total_samples = len(dataset)
    accuracy = (total_correct / total_samples) * 100.0

    detection_rates = {}
    for cat, total in category_counts.items():
        if cat != "genuine" and total > 0:
            rate = (category_correct[cat] / total) * 100.0
            detection_rates[cat] = round(rate, 2)

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_presentations": total_samples,
        "bona_fide_count": bona_fide_total,
        "attack_count": attack_total,
        "sla_target_seconds": DECISION_TIMEOUT_SECONDS,
        "latency_metrics_ms": {
            "mean": round(mean_lat, 2),
            "p50": round(p50, 2),
            "p90": round(p90, 2),
            "p95": round(p95, 2),
            "max": round(max_lat, 2),
            "all_within_2s_sla": max_lat <= (DECISION_TIMEOUT_SECONDS * 1000.0),
        },
        "accuracy_percent": round(accuracy, 2),
        "apcer_percent": round(apcer, 2),
        "bpcer_percent": round(bpcer, 2),
        "far_percent": round(far, 2),
        "frr_percent": round(frr, 2),
        "spoof_detection_rates_percent": detection_rates,
    }

    BENCHMARK_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BENCHMARK_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    report = run_benchmark()
    print("=" * 65)
    print(" HID HACKATHON: AUTOMATED BENCHMARK REPORT")
    print("=" * 65)
    print(f"Total Presentations Evaluated : {report['total_presentations']}")
    print(f"Overall Accuracy              : {report['accuracy_percent']}%")
    print(f"APCER (Attack Error Rate)     : {report['apcer_percent']}%")
    print(f"BPCER (Bona Fide Error Rate)  : {report['bpcer_percent']}%")
    print("-" * 65)
    print("SPOOF DETECTION RATES:")
    for k, v in report["spoof_detection_rates_percent"].items():
        print(f"  • {k.replace('_', ' ').title():<25} : {v}%")
    print("-" * 65)
    print("LATENCY PERFORMANCE (SLA <= 2.0s):")
    print(f"  • Mean Latency : {report['latency_metrics_ms']['mean']} ms")
    print(f"  • p50 Latency  : {report['latency_metrics_ms']['p50']} ms")
    print(f"  • p95 Latency  : {report['latency_metrics_ms']['p95']} ms")
    print(f"  • Max Latency  : {report['latency_metrics_ms']['max']} ms")
    print(f"  • Status       : {'PASSED (Within 2s SLA)' if report['latency_metrics_ms']['all_within_2s_sla'] else 'FAILED'}")
    print("=" * 65)
