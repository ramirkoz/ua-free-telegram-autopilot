from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_SIGNATURE_FIELDS = {"signature", "signature_b64", "signature_algorithm", "key_id"}


def canonical_manifest_bytes(data: dict[str, Any]) -> bytes:
    payload = {k: v for k, v in data.items() if k not in _SIGNATURE_FIELDS}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _public_key_pem() -> bytes:
    raw = str(os.getenv("UA_FREE_AUTOPILOT_UPDATE_PUBLIC_KEY_PEM", "") or "").strip()
    if raw:
        return raw.replace("\\n", "\n").encode("utf-8")
    root = Path(__file__).resolve().parents[2]
    candidate = root / "UPDATE_SIGNING_PUBLIC_KEY.pem"
    if candidate.is_file():
        return candidate.read_bytes()
    return b""


def signing_key_available() -> bool:
    return bool(_public_key_pem().strip())


def verify_manifest_signature(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    if str(data.get("signature_algorithm") or "").strip().casefold() != "ed25519":
        return False
    signature_text = str(data.get("signature_b64") or data.get("signature") or "").strip()
    pem = _public_key_pem()
    if not signature_text or not pem:
        return False
    try:
        public = serialization.load_pem_public_key(pem)
        if not isinstance(public, Ed25519PublicKey):
            return False
        signature = base64.b64decode(signature_text, validate=True)
        public.verify(signature, canonical_manifest_bytes(data))
        return True
    except Exception:
        return False
