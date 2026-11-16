#!/usr/bin/env python3
"""
run_demo.py
Demonstration script executing the Spectral Face Recognition pipeline end-to-end.
"""

import io
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app, pca, store
import config


def create_sample_face(seed: int, base_color: int, noise_scale: int = 15) -> bytes:
    """Creates a sample face image for testing."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (100, 100), color=(base_color, base_color, base_color))
    draw = ImageDraw.Draw(img)
    # Head contour
    draw.ellipse([20, 20, 80, 80], outline=(220, 220, 220), fill=(base_color + 20, base_color + 20, base_color + 20))
    # Eyes
    draw.ellipse([35, 40, 45, 50], fill=(30, 30, 30))
    draw.ellipse([55, 40, 65, 50], fill=(30, 30, 30))
    # Nose & Mouth
    draw.line([50, 48, 50, 58], fill=(50, 50, 50), width=2)
    draw.rectangle([40, 66, 60, 72], fill=(60, 60, 60))
    
    # Add unique texture
    arr = np.array(img, dtype=np.int16)
    noise = rng.integers(-noise_scale, noise_scale, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def print_section(title: str):
    print(f"\n{'=' * 65}")
    print(f" {title}")
    print('=' * 65)


def main():
    client = TestClient(app)
    
    print_section("1. INITIAL HEALTH CHECK (/health)")
    res = client.get("/health")
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")

    print_section("2. REGISTERING FIRST FACE: 'Alice' (/register)")
    alice_img = create_sample_face(seed=101, base_color=110)
    res = client.post(
        "/register",
        data={"name": "Alice"},
        files={"image": ("alice.png", alice_img, "image/png")}
    )
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")
    print(">> Note: Needs >= 2 faces to train PCA surrogate covariance matrix L = A^T A.")

    print_section("3. REGISTERING SECOND FACE: 'Bob' (/register)")
    bob_img = create_sample_face(seed=202, base_color=170)
    res = client.post(
        "/register",
        data={"name": "Bob"},
        files={"image": ("bob.png", bob_img, "image/png")}
    )
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")

    print_section("4. REGISTERING THIRD FACE: 'Charlie' (/register)")
    charlie_img = create_sample_face(seed=303, base_color=140)
    res = client.post(
        "/register",
        data={"name": "Charlie"},
        files={"image": ("charlie.png", charlie_img, "image/png")}
    )
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")

    print_section("5. LIST REGISTERED USERS (/users)")
    res = client.get("/users")
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")

    print_section("6. PCA ENGINE & VECTOR STORE STATUS")
    print(f"Model is trained      : {pca.is_trained}")
    print(f"Mean face Ψ shape     : {pca.mean_face.shape} (100x100 = 10,000 pixels)")
    print(f"Eigenface Basis U     : {pca.U.shape} (pixels x components)")
    print(f"Vector Store Users    : {store.list_users()}")
    print(f"Vector Store Size     : {store.count()} vectors of dimension {store._vectors.shape[1]}")

    print_section("7. VERIFYING MATCH: 'Alice' Photo (/verify)")
    # Test slightly altered Alice image (simulating different capture)
    alice_verify_img = create_sample_face(seed=101, base_color=112, noise_scale=20)
    res = client.post(
        "/verify",
        files={"image": ("alice_test.png", alice_verify_img, "image/png")}
    )
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")

    print_section("8. VERIFYING MATCH: 'Bob' Photo (/verify)")
    bob_verify_img = create_sample_face(seed=202, base_color=168, noise_scale=20)
    res = client.post(
        "/verify",
        files={"image": ("bob_test.png", bob_verify_img, "image/png")}
    )
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")

    print_section("9. VERIFYING UNKNOWN / UNREGISTERED PERSON (/verify)")
    intruder_img = create_sample_face(seed=999, base_color=50, noise_scale=40)
    res = client.post(
        "/verify",
        files={"image": ("intruder.png", intruder_img, "image/png")}
    )
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")

    print_section("10. DELETING USER: 'Charlie' (/users/Charlie)")
    res = client.delete("/users/Charlie")
    print(f"Status Code : {res.status_code}")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")

    print_section("11. USERS AFTER DELETION & RETRAIN")
    res = client.get("/users")
    print(f"Response    : {json.dumps(res.json(), indent=2)}")
    print(f"Updated Eigenface Basis U shape: {pca.U.shape}")

    print_section("DEMO RUN COMPLETE")


if __name__ == "__main__":
    main()
