"""Canonical form for deed records.

The same deed must always produce the same bytes, otherwise a genuine deed
would fail verification. We therefore:

* normalise every string to Unicode NFC (Bangla text can be typed with
  different code point sequences that look identical),
* convert Bangla digits (০-৯) to ASCII digits,
* collapse runs of whitespace and trim,
* serialise JSON with sorted keys, no spaces, UTF-8 (an RFC 8785-style subset:
  only strings, integers, booleans, null, lists and objects are allowed;
  floats are rejected because their text form is ambiguous).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_WS = re.compile(r"\s+")


class CanonicalError(ValueError):
    """Raised when a value cannot be put in canonical form."""


def norm_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = value.translate(_BN_DIGITS)
    return _WS.sub(" ", value).strip()


def normalize(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CanonicalError("floats are not allowed in canonical records; use integers")
    if isinstance(value, str):
        return norm_text(value)
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise CanonicalError("object keys must be strings")
            nk = norm_text(k)
            if nk in out:
                raise CanonicalError(f"duplicate key after normalisation: {nk!r}")
            out[nk] = normalize(v)
        return out
    raise CanonicalError(f"unsupported type: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_hash(value: Any) -> str:
    return sha256_hex(canonical_bytes(value))
