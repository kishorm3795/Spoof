"""
backend/offline/audit_log.py
----------------------------
Tamper-evident, privacy-preserving local offline event log storage.
Surprise Challenge 2 requirement:
"Store only minimum temporary information."

Architectural principles:
1. Zero Biometric Storage: Kiosk NEVER writes face images or raw embeddings to local disk.
2. Pseudonymized Identity: User names are hashed with a local HMAC key.
3. Cryptographic Tamper-Evidence: Append-only hash chain where each event incorporates
   the SHA-256 hash of the preceding event, sealed with an HMAC signature.
4. Minimal Retention: Local events are marked for purging immediately after synchronization.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import OFFLINE_AUDIT_LOG_PATH, OFFLINE_HMAC_SECRET, OFFLINE_MAX_LOCAL_EVENTS


class OfflineAuditLog:
    """
    Manages local offline event logs with cryptographic chain integrity
    and minimal privacy-preserving metadata.
    """

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(
        self,
        log_path: Path = OFFLINE_AUDIT_LOG_PATH,
        secret_key: str = OFFLINE_HMAC_SECRET,
    ):
        self.log_path = Path(log_path)
        self.secret_key = secret_key.encode("utf-8")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _hash_pseudonym(self, user_name: str) -> str:
        """Hashes the user identity to prevent storing plaintext PII locally."""
        return hmac.new(
            self.secret_key,
            f"user:{user_name.strip().lower()}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:24]

    def _compute_event_hash(self, payload: dict) -> str:
        """Computes SHA-256 over serialized canonical JSON."""
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _compute_signature(self, event_hash: str) -> str:
        """Computes HMAC signature to prevent local tampering."""
        return hmac.new(self.secret_key, event_hash.encode("utf-8"), hashlib.sha256).hexdigest()

    def _get_last_hash(self) -> str:
        """Reads the hash of the last committed event in the chain."""
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            return self.GENESIS_HASH

        last_hash = self.GENESIS_HASH
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        last_hash = record.get("event_hash", last_hash)
                    except json.JSONDecodeError:
                        continue
        return last_hash

    def append_event(
        self,
        user_name: str,
        zone: str,
        decision: str,
        reason: str,
        dt: Optional[datetime] = None,
    ) -> dict:
        """
        Appends a minimal, tamper-evident audit record to local disk.
        Notice: NO raw image or biometric embeddings are stored.
        """
        now = dt or datetime.now()
        prev_hash = self._get_last_hash()

        payload = {
            "event_id": str(uuid.uuid4()),
            "timestamp": now.isoformat(),
            "pseudonym_hash": self._hash_pseudonym(user_name),
            "zone": str(zone),
            "decision": str(decision),
            "reason": str(reason),
            "offline_mode": True,
            "synced": False,
            "prev_hash": prev_hash,
        }

        event_hash = self._compute_event_hash(payload)
        signature = self._compute_signature(event_hash)

        record = {
            **payload,
            "event_hash": event_hash,
            "signature": signature,
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return record

    def read_all_events(self) -> list[dict]:
        """Reads all local events from disk."""
        if not self.log_path.exists():
            return []
        events = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events

    def get_pending_sync_events(self) -> list[dict]:
        """Returns all offline events waiting for cloud synchronization."""
        return [e for e in self.read_all_events() if not e.get("synced", False)]

    def verify_chain_integrity(self) -> tuple[bool, str]:
        """
        Validates the hash chain and signatures across all local records.
        Detects unauthorized local file modification or deletion.
        """
        events = self.read_all_events()
        if not events:
            return True, "Audit log empty (valid)"

        expected_prev = self.GENESIS_HASH
        for idx, record in enumerate(events):
            if record.get("prev_hash") != expected_prev:
                return False, f"Broken hash chain at event index {idx} ({record.get('event_id')})"

            # Recompute hash without signature and event_hash
            payload = {k: v for k, v in record.items() if k not in ["event_hash", "signature"]}
            expected_hash = self._compute_event_hash(payload)
            if record.get("event_hash") != expected_hash:
                return False, f"Hash mismatch at event index {idx}"

            expected_sig = self._compute_signature(expected_hash)
            if record.get("signature") != expected_sig:
                return False, f"Signature forgery detected at event index {idx}"

            expected_prev = expected_hash

        return True, f"Audit log verified: {len(events)} events with valid cryptographic chain"

    def mark_synced(self, event_ids: list[str]) -> int:
        """Flags events as successfully synchronized to central server."""
        id_set = set(event_ids)
        events = self.read_all_events()
        updated_count = 0

        for e in events:
            if e.get("event_id") in id_set and not e.get("synced"):
                e["synced"] = True
                updated_count += 1

        if updated_count > 0:
            with open(self.log_path, "w", encoding="utf-8") as f:
                for e in events:
                    f.write(json.dumps(e) + "\n")

        return updated_count

    def clear(self) -> None:
        """Clears local audit log (used for testing or maintenance)."""
        if self.log_path.exists():
            self.log_path.unlink()
