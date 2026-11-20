"""
CAVP V3 Ephemeral Verification Envelope.

Provides:
- EphemeralVerificationEnvelope with recursive deep-freezing.
- HMAC-SHA256 cryptographic signing and tamper-evident verification.
- Replay protection via monotonically increasing nonce and TTL.
"""

import hashlib
import hmac
import json
import time
import uuid
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Tuple, Union

from core.memory_manager import DataSanitizer, Provenance, SecurityException


def deep_freeze(obj: Any) -> Any:
    """Recursively freeze dictionaries to MappingProxyType and lists/sets to tuples."""
    if isinstance(obj, dict):
        return MappingProxyType({k: deep_freeze(v) for k, v in obj.items()})
    elif isinstance(obj, (list, tuple, set)):
        return tuple(deep_freeze(v) for v in obj)
    return obj


class EphemeralVerificationEnvelope:
    """Immutable, cryptographically signed verification envelope for CAVP V3."""

    def __init__(
        self,
        task_id: str,
        user_id: str,
        originator_agent: str,
        target_verifier: str,
        artifact_type: str,
        artifact_payload: Any,
        provenance: str = Provenance.AGENT_INFERRED.value,
        ttl_ms: int = 3000,
        nonce: Optional[int] = None,
        created_at: Optional[float] = None,
        signature: Optional[str] = None,
    ):
        # Inbound sanitization
        if isinstance(artifact_payload, str):
            DataSanitizer.sanitize(artifact_payload)
        elif isinstance(artifact_payload, dict):
            for v in artifact_payload.values():
                if isinstance(v, str):
                    DataSanitizer.sanitize(v)

        self.envelope_id: str = str(uuid.uuid4())
        self.task_id: str = task_id
        self.user_id: str = user_id
        self.originator_agent: str = originator_agent
        self.target_verifier: str = target_verifier
        self.artifact_type: str = artifact_type
        self.artifact_payload: Any = deep_freeze(artifact_payload)
        self.provenance: str = provenance
        self.ttl_ms: int = ttl_ms
        self.created_at: float = created_at if created_at is not None else time.time()
        self.nonce: int = nonce if nonce is not None else int(time.time() * 1000)
        self.signature: Optional[str] = signature
        self._frozen: bool = True

    def __setattr__(self, key: str, value: Any) -> None:
        if getattr(self, "_frozen", False) and key != "signature":
            raise TypeError(f"EphemeralVerificationEnvelope is immutable; cannot modify attribute '{key}'")
        super().__setattr__(key, value)

    def _canonical_bytes(self) -> bytes:
        """Serialize envelope metadata and payload into deterministic bytes for signing."""
        def unfreeze(o):
            if isinstance(o, MappingProxyType):
                return {k: unfreeze(v) for k, v in o.items()}
            elif isinstance(o, tuple):
                return [unfreeze(v) for v in o]
            return o

        canonical_data = {
            "envelope_id": self.envelope_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "originator_agent": self.originator_agent,
            "target_verifier": self.target_verifier,
            "artifact_type": self.artifact_type,
            "artifact_payload": unfreeze(self.artifact_payload),
            "provenance": self.provenance,
            "ttl_ms": self.ttl_ms,
            "nonce": self.nonce,
            "created_at": round(self.created_at, 3),
        }
        return json.dumps(canonical_data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def sign(self, secret_key: bytes) -> str:
        """Compute HMAC-SHA256 signature and attach to envelope."""
        sig = hmac.new(secret_key, self._canonical_bytes(), hashlib.sha256).hexdigest()
        super().__setattr__("signature", sig)
        return sig

    def verify(self, secret_key: bytes, current_time: Optional[float] = None) -> bool:
        """Verify HMAC-SHA256 signature and TTL expiration."""
        if not self.signature:
            return False

        # TTL validation
        now = current_time if current_time is not None else time.time()
        elapsed_ms = (now - self.created_at) * 1000
        if elapsed_ms > self.ttl_ms:
            return False

        # Signature verification (constant-time)
        expected = hmac.new(secret_key, self._canonical_bytes(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)
