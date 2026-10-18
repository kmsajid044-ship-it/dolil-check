"""Ed25519 office keys.

Each office (sub-registry, AC Land, the log operator) has its own key.
Public keys are published with a validity window; a leaked key is revoked
from a date onward, and signatures it made after that date are distrusted.

In production the private keys live in an HSM. In this prototype they are
PEM files under the data directory (never commit them).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _raw_public(pub: Ed25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id_for(pub: Ed25519PublicKey) -> str:
    return hashlib.sha256(_raw_public(pub)).hexdigest()[:16]


@dataclass
class PublicKeyInfo:
    key_id: str
    office_id: str
    role: str  # "sub_registry" | "ac_land" | "log"
    public_key: str  # base64url raw 32 bytes
    valid_from: str  # ISO date
    revoked_from: Optional[str] = None  # ISO date; signatures dated on/after this are invalid

    def public(self) -> Ed25519PublicKey:
        return Ed25519PublicKey.from_public_bytes(b64u_decode(self.public_key))


@dataclass
class KeyRing:
    directory: Optional[Path] = None
    infos: Dict[str, PublicKeyInfo] = field(default_factory=dict)
    _private: Dict[str, Ed25519PrivateKey] = field(default_factory=dict, repr=False)

    # ---------- persistence ----------
    @classmethod
    def load(cls, directory: os.PathLike | str | None) -> "KeyRing":
        ring = cls(Path(directory) if directory else None)
        if ring.directory is None or not (ring.directory / "keys.json").exists():
            return ring
        data = json.loads((ring.directory / "keys.json").read_text("utf-8"))
        for item in data:
            info = PublicKeyInfo(**item)
            ring.infos[info.key_id] = info
            pem = ring.directory / "private" / f"{info.key_id}.pem"
            if pem.exists():
                ring._private[info.key_id] = serialization.load_pem_private_key(pem.read_bytes(), None)
        return ring

    def save(self) -> None:
        if self.directory is None:
            return
        (self.directory / "private").mkdir(parents=True, exist_ok=True)
        (self.directory / "keys.json").write_text(
            json.dumps([asdict(i) for i in self.infos.values()], indent=2, ensure_ascii=False), "utf-8"
        )
        for kid, priv in self._private.items():
            path = self.directory / "private" / f"{kid}.pem"
            if not path.exists():
                path.write_bytes(
                    priv.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                )
                os.chmod(path, 0o600)

    # ---------- keys ----------
    def create(self, office_id: str, role: str, valid_from: str) -> PublicKeyInfo:
        priv = Ed25519PrivateKey.generate()
        info = PublicKeyInfo(
            key_id=key_id_for(priv.public_key()),
            office_id=office_id,
            role=role,
            public_key=b64u(_raw_public(priv.public_key())),
            valid_from=valid_from,
        )
        self.infos[info.key_id] = info
        self._private[info.key_id] = priv
        self.save()
        return info

    def active_key(self, office_id: str) -> PublicKeyInfo:
        for info in self.infos.values():
            if info.office_id == office_id and info.revoked_from is None and info.key_id in self._private:
                return info
        raise KeyError(f"no active signing key for office {office_id!r}")

    def revoke(self, key_id: str, from_date: str) -> None:
        self.infos[key_id].revoked_from = from_date
        self.save()

    def public_listing(self) -> list:
        return [asdict(i) for i in self.infos.values()]

    # ---------- sign / verify ----------
    def sign(self, key_id: str, message: bytes) -> str:
        return b64u(self._private[key_id].sign(message))

    def verify(self, key_id: str, message: bytes, signature: str, signed_on: Optional[str] = None) -> Tuple[bool, str]:
        return verify_with_listing(self.infos, key_id, message, signature, signed_on)


def verify_with_listing(
    infos: Dict[str, PublicKeyInfo], key_id: str, message: bytes, signature: str, signed_on: Optional[str] = None
) -> Tuple[bool, str]:
    """Verify using only public information (usable offline)."""
    info = infos.get(key_id)
    if info is None:
        return False, "unknown key"
    if signed_on is not None:
        if signed_on < info.valid_from:
            return False, "signed before the key was valid"
        if info.revoked_from is not None and signed_on >= info.revoked_from:
            return False, "key was revoked on or before the signing date"
    try:
        info.public().verify(b64u_decode(signature), message)
    except (InvalidSignature, ValueError):
        return False, "bad signature"
    return True, "ok"


# Domain-separated messages so a signature for one purpose can never be replayed for another.
# `dolil-seal/v1` is the original wire-level protocol name, not visible branding. Keep it forever:
# changing these bytes would invalidate every existing deed, baseline, mutation and signed tree head.
def deed_message(record_hash: str) -> bytes:
    return b"dolil-seal/v1/deed:" + bytes.fromhex(record_hash)


def baseline_message(record_hash: str) -> bytes:
    return b"dolil-seal/v1/baseline:" + bytes.fromhex(record_hash)


def mutation_message(record_hash: str) -> bytes:
    return b"dolil-seal/v1/mutation:" + bytes.fromhex(record_hash)


def sth_message(tree_size: int, root_hex: str, timestamp: str) -> bytes:
    return f"dolil-seal/v1/sth:{tree_size}:{root_hex}:{timestamp}".encode("ascii")
