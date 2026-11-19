"""
backend/offline/totp_fallback.py
--------------------------------
Offline emergency fallback verification using RFC 6238 Time-Based One-Time Passwords (TOTP).
Surprise Challenge 2 requirement:
"Provide fallback verification."

Enables emergency clearance and step-up verification when network connection
is unavailable by computing cryptographic HMAC-SHA1 tokens locally based on
hardware real-time clock (RTC).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime
from typing import Optional

from config import EMERGENCY_TOTP_SECRET


class TOTPFallback:
    """
    Implements RFC 6238 TOTP verification and emergency offline override codes.
    """

    MASTER_OVERRIDE_PIN = "994821"  # Physical emergency key for facility security officers

    def __init__(self, base32_secret: str = EMERGENCY_TOTP_SECRET, time_step: int = 30):
        self.secret = base32_secret
        self.time_step = time_step
        self._consumed_tokens: set[str] = set()

    def _get_key_bytes(self) -> bytes:
        """Decodes base32 secret with padding handling."""
        normalized = self.secret.strip().upper()
        missing_padding = len(normalized) % 8
        if missing_padding:
            normalized += "=" * (8 - missing_padding)
        return base64.b32decode(normalized)

    def generate_token(self, for_time: Optional[float] = None) -> str:
        """Generates a 6-digit TOTP code for the specified epoch timestamp."""
        t = for_time if for_time is not None else time.time()
        counter = int(t // self.time_step)

        counter_bytes = struct.pack(">Q", counter)
        key = self._get_key_bytes()

        mac = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        offset = mac[-1] & 0x0F
        binary = (
            ((mac[offset] & 0x7F) << 24)
            | ((mac[offset + 1] & 0xFF) << 16)
            | ((mac[offset + 2] & 0xFF) << 8)
            | (mac[offset + 3] & 0xFF)
        )
        token = str(binary % 1_000_000).zfill(6)
        return token

    def verify_token(
        self,
        token: str,
        for_time: Optional[float] = None,
        allowed_drift_steps: int = 1,
    ) -> bool:
        """
        Validates token against time-step window with drift tolerance (±1 step = 30s).
        Enforces single-use replay prevention.
        """
        cleaned = token.strip()
        if not cleaned.isdigit() or len(cleaned) != 6:
            return False

        t = for_time if for_time is not None else time.time()
        current_step = int(t // self.time_step)

        # Check drift window: [-allowed_drift_steps, +allowed_drift_steps]
        for step_offset in range(-allowed_drift_steps, allowed_drift_steps + 1):
            check_time = (current_step + step_offset) * self.time_step
            expected_token = self.generate_token(check_time)
            if hmac.compare_digest(cleaned, expected_token):
                token_key = f"{cleaned}:{current_step + step_offset}"
                if token_key in self._consumed_tokens:
                    # Prevent replay attacks
                    return False
                self._consumed_tokens.add(token_key)
                return True

        return False

    def verify_fallback(
        self,
        verification_code: str,
        user_name: str,
        zone: str,
        dt: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        """
        Evaluates emergency fallback verification (TOTP or Master PIN).

        Returns:
            (is_valid, description_reason)
        """
        code = verification_code.strip()

        # 1. Check Master Override PIN (for physical security keyholder)
        if code == self.MASTER_OVERRIDE_PIN:
            return True, "Emergency master security override accepted"

        # 2. Check RFC 6238 TOTP
        t = dt.timestamp() if dt else time.time()
        if self.verify_token(code, for_time=t):
            return True, f"Offline TOTP verified successfully for {user_name} at {zone}"

        return False, "Invalid or expired emergency verification code"
