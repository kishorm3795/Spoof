from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).resolve().parent.parent
MODEL_DIR      = BASE_DIR / "models"
DATA_DIR       = BASE_DIR / "data"
CHROMA_DB_PATH = BASE_DIR / "backend" / "chroma_db"

MODEL_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

EIGENFACES_PATH = MODEL_DIR / "eigenfaces.npz"   # stores U and mean_face
RAW_FACES_PATH  = DATA_DIR  / "raw_faces.npz"    # stores raw pixel vectors + labels
VECTOR_STORE_PATH = DATA_DIR / "vector_store.npz"

# ── PCA settings ────────────────────────────────────────────────────────
IMG_SIZE = 100          # images resized to IMG_SIZE × IMG_SIZE
IMG_DIM  = IMG_SIZE * IMG_SIZE   # flattened vector length = 10 000
K        = 50           # number of eigenfaces (top-K components)

# ── Verification threshold ──────────────────────────────────────────────
# Cosine distance (0 = identical, 2 = opposite).
THRESHOLD = 0.35        # distances below this → accepted match
IDENTITY_HIGH_CONFIDENCE = 0.20  # distance <= 0.20 indicates very high confidence match

# ── Primary Challenge: Anti-Spoofing & Liveness Settings ───────────────
DECISION_TIMEOUT_SECONDS = 2.0   # Hard deadline for kiosk decision

# Liveness classification thresholds (score 0.0 to 1.0)
LIVENESS_CONFIDENCE_THRESHOLD = 0.70  # >= 0.70 is deemed genuine live human
LIVENESS_BORDERLINE_MIN       = 0.45  # 0.45 - 0.69 triggers REQUEST VERIFICATION
# < 0.45 is deemed DENY / presentation attack

# Sub-detector tuning constants
FREQ_HIGH_LOW_RATIO_MIN  = 0.065 # Living skin maintains high-frequency texture gradient
GLARE_SPECULAR_MAX_RATIO = 0.045 # Screen replays exhibit excessive specular highlight areas
MOIRE_BANDING_PEAK_MAX   = 3.800 # Digital displays generate periodic 2D spatial frequency spikes
DEPTH_DISPARITY_MIN      = 0.040 # 3D natural faces exhibit surface normal gradient divergence

# Weights for multi-spoof ensemble
WEIGHT_FREQUENCY = 0.25
WEIGHT_GLARE     = 0.25
WEIGHT_MOIRE     = 0.25
WEIGHT_DEPTH     = 0.25

# ── Surprise Challenge 1: Campus Schedule Settings ──────────────────────
DEFAULT_CAMPUS_ZONES = [
    "main_gate",
    "engineering_lab",
    "library",
    "admin_office",
    "dormitory",
    "server_room_high_security",
]

DEFAULT_USER_ROLES = [
    "student",
    "faculty",
    "staff",
    "visitor",
    "contractor",
    "security_admin",
]

AFTER_HOURS_GRACE_MINUTES = 60 # Allow step-up verification during 60 min after curfew

# ── Surprise Challenge 2: Offline Mode & Safe Access Settings ───────────
OFFLINE_STRICTNESS_MULTIPLIER = 1.15 # Require 15% stricter threshold when offline
OFFLINE_AUDIT_LOG_PATH        = DATA_DIR / "offline_audit.jsonl"
OFFLINE_SYNC_BACKLOG_PATH     = DATA_DIR / "offline_sync_backlog.json"
OFFLINE_HMAC_SECRET           = "hid-kiosk-offline-tamper-proof-secret-2026"
EMERGENCY_TOTP_SECRET         = "JBSWY3DPEHPK3PXP" # Base32 test secret for RFC 6238 TOTP
OFFLINE_MAX_LOCAL_EVENTS      = 500 # Privacy: roll over or purge minimal events
