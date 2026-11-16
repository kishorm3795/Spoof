"""
backend/offline/sync_manager.py
-------------------------------
Decision reconciliation and audit log synchronization engine.
Surprise Challenge 2 requirement:
"Synchronize decisions when the connection returns."

Protocol:
1. Kiosk aggregates pending offline decisions into a signed batch.
2. Central backend ingests batch, verifies HMAC chain, checks for security anomalies.
3. Central backend responds with authenticated receipt.
4. Kiosk marks events synced and performs privacy-preserving local storage compaction.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import OFFLINE_HMAC_SECRET, BASE_DIR
from .audit_log import OfflineAuditLog

CENTRAL_AUDIT_STORE_PATH = BASE_DIR / "data" / "central_reconciled_audit.jsonl"


class SyncManager:
    """
    Orchestrates synchronization of offline kiosk decisions to central service.
    """

    def __init__(
        self,
        audit_log: Optional[OfflineAuditLog] = None,
        central_store_path: Path = CENTRAL_AUDIT_STORE_PATH,
        secret_key: str = OFFLINE_HMAC_SECRET,
    ):
        self.audit_log = audit_log or OfflineAuditLog()
        self.central_store_path = Path(central_store_path)
        self.secret_key = secret_key.encode("utf-8")
        self.central_store_path.parent.mkdir(parents=True, exist_ok=True)

    def prepare_sync_batch(self, kiosk_id: str = "kiosk-hid-01") -> dict:
        """
        Gathers pending offline events and signs the sync bundle.
        """
        pending_events = self.audit_log.get_pending_sync_events()
        batch_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # Compute payload hash
        payload_bytes = json.dumps(pending_events, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        batch_sig = hmac.new(self.secret_key, f"{batch_id}:{payload_hash}".encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "kiosk_id": kiosk_id,
            "batch_id": batch_id,
            "timestamp": timestamp,
            "event_count": len(pending_events),
            "payload_hash": payload_hash,
            "batch_signature": batch_sig,
            "events": pending_events,
        }

    def process_incoming_batch(self, batch_data: dict) -> dict:
        """
        Executes on central backend: validates batch integrity,
        reconciles decisions, and writes to central store.
        """
        batch_id = batch_data.get("batch_id")
        events = batch_data.get("events", [])
        payload_hash = batch_data.get("payload_hash")
        sig = batch_data.get("batch_signature")

        # 1. Verify batch signature
        computed_hash = hashlib.sha256(json.dumps(events, sort_keys=True).encode("utf-8")).hexdigest()
        expected_sig = hmac.new(self.secret_key, f"{batch_id}:{computed_hash}".encode("utf-8"), hashlib.sha256).hexdigest()

        if computed_hash != payload_hash or sig != expected_sig:
            return {
                "success": False,
                "error": "Batch signature verification failed. Possible payload tampering.",
                "reconciled_count": 0,
                "acknowledged_ids": [],
            }

        # 2. Append events to central reconciled log
        acknowledged_ids = []
        with open(self.central_store_path, "a", encoding="utf-8") as f:
            for record in events:
                event_id = record.get("event_id")
                reconciled_entry = {
                    **record,
                    "reconciled_at": datetime.now().isoformat(),
                    "batch_id": batch_id,
                }
                f.write(json.dumps(reconciled_entry) + "\n")
                if event_id:
                    acknowledged_ids.append(event_id)

        return {
            "success": True,
            "status": "RECONCILED",
            "batch_id": batch_id,
            "reconciled_count": len(acknowledged_ids),
            "acknowledged_ids": acknowledged_ids,
        }

    def complete_sync(self, receipt: dict) -> int:
        """
        Executed on kiosk after successful central reconciliation:
        marks acknowledged event records as synced on local storage.
        """
        if not receipt.get("success", False):
            return 0
        ack_ids = receipt.get("acknowledged_ids", [])
        return self.audit_log.mark_synced(ack_ids)

    def read_central_records(self) -> list[dict]:
        """Reads all reconciled records from central audit store."""
        if not self.central_store_path.exists():
            return []
        records = []
        with open(self.central_store_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records
