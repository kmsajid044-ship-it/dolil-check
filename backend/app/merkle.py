"""Append-only Merkle log, following RFC 6962 / RFC 9162 (Certificate Transparency).

Leaf hash  = SHA-256(0x00 || leaf_data)
Node hash  = SHA-256(0x01 || left || right)

The log can prove two things to anyone holding only a signed tree head:
* inclusion: a given entry is in the tree of size n,
* consistency: the tree of size m is a prefix of the tree of size n,
  i.e. nothing was rewritten or removed between two published heads.
"""

from __future__ import annotations

import hashlib
from typing import List, Sequence

EMPTY_ROOT = hashlib.sha256(b"").digest()


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    """Largest power of two strictly smaller than n (n >= 2)."""
    k = 1
    while k << 1 < n:
        k <<= 1
    return k


def mth(leaves: Sequence[bytes]) -> bytes:
    """Merkle tree hash over a list of *leaf hashes*."""
    n = len(leaves)
    if n == 0:
        return EMPTY_ROOT
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node_hash(mth(leaves[:k]), mth(leaves[k:]))


def inclusion_path(m: int, leaves: Sequence[bytes]) -> List[bytes]:
    n = len(leaves)
    if not 0 <= m < n:
        raise IndexError("leaf index out of range")
    if n == 1:
        return []
    k = _split(n)
    if m < k:
        return inclusion_path(m, leaves[:k]) + [mth(leaves[k:])]
    return inclusion_path(m - k, leaves[k:]) + [mth(leaves[:k])]


def _subproof(m: int, leaves: Sequence[bytes], complete: bool) -> List[bytes]:
    n = len(leaves)
    if m == n:
        return [] if complete else [mth(leaves)]
    k = _split(n)
    if m <= k:
        return _subproof(m, leaves[:k], complete) + [mth(leaves[k:])]
    return _subproof(m - k, leaves[k:], False) + [mth(leaves[:k])]


def consistency_proof(m: int, leaves: Sequence[bytes]) -> List[bytes]:
    n = len(leaves)
    if not 0 < m <= n:
        raise ValueError("need 0 < m <= n")
    if m == n:
        return []
    return _subproof(m, leaves, True)


def verify_inclusion(lhash: bytes, index: int, size: int, path: Sequence[bytes], root: bytes) -> bool:
    if index >= size or index < 0:
        return False
    fn, sn, r = index, size - 1, lhash
    for p in path:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


def verify_consistency(first: int, second: int, root1: bytes, root2: bytes, proof: Sequence[bytes]) -> bool:
    if first <= 0 or first > second:
        return False
    if first == second:
        return len(proof) == 0 and root1 == root2
    proof = list(proof)
    if first & (first - 1) == 0:  # exact power of two
        proof = [root1] + proof
    if not proof:
        return False
    fn, sn = first - 1, second - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = proof[0]
    for c in proof[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr = node_hash(c, fr)
            sr = node_hash(c, sr)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            sr = node_hash(sr, c)
        fn >>= 1
        sn >>= 1
    return sn == 0 and fr == root1 and sr == root2


class MerkleLog:
    """In-memory view of the log's leaf hashes (the database is the source of truth)."""

    def __init__(self, leaf_hashes: Sequence[bytes] = ()):
        self._leaves: List[bytes] = list(leaf_hashes)

    def __len__(self) -> int:
        return len(self._leaves)

    def append(self, data: bytes) -> int:
        self._leaves.append(leaf_hash(data))
        return len(self._leaves) - 1

    def leaf(self, index: int) -> bytes:
        return self._leaves[index]

    def root(self, size: int | None = None) -> bytes:
        size = len(self._leaves) if size is None else size
        if not 0 <= size <= len(self._leaves):
            raise ValueError("size out of range")
        return mth(self._leaves[:size])

    def inclusion(self, index: int, size: int | None = None) -> List[bytes]:
        size = len(self._leaves) if size is None else size
        if not 0 < size <= len(self._leaves):
            raise ValueError("size out of range")
        return inclusion_path(index, self._leaves[:size])

    def consistency(self, first: int, second: int | None = None) -> List[bytes]:
        second = len(self._leaves) if second is None else second
        if not 0 < second <= len(self._leaves):
            raise ValueError("size out of range")
        return consistency_proof(first, self._leaves[:second])
