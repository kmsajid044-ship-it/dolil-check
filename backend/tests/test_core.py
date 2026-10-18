import hashlib
import unicodedata
import unittest

from app import canonical, merkle
from app.signing import KeyRing, deed_message


class CanonicalTests(unittest.TestCase):
    def test_bangla_digits_and_ascii_digits_hash_the_same(self):
        a = canonical.record_hash({"dag": "১২৩", "area": 10})
        b = canonical.record_hash({"dag": "123", "area": 10})
        self.assertEqual(a, b)

    def test_nfc_and_nfd_hash_the_same(self):
        word = "রহিম"
        nfd = unicodedata.normalize("NFD", word)
        self.assertEqual(canonical.record_hash({"n": word}), canonical.record_hash({"n": nfd}))

    def test_whitespace_and_key_order_do_not_matter(self):
        a = canonical.canonical_bytes({"b": "  x   y ", "a": 1})
        b = canonical.canonical_bytes({"a": 1, "b": "x y"})
        self.assertEqual(a, b)
        self.assertEqual(a, b'{"a":1,"b":"x y"}')

    def test_one_character_change_changes_hash(self):
        self.assertNotEqual(
            canonical.record_hash({"area": "10.000"}), canonical.record_hash({"area": "16.000"})
        )

    def test_floats_rejected(self):
        with self.assertRaises(canonical.CanonicalError):
            canonical.canonical_bytes({"area": 10.5})


class MerkleTests(unittest.TestCase):
    def leaves(self, n):
        return [merkle.leaf_hash(f"entry-{i}".encode()) for i in range(n)]

    def test_empty_root_is_sha256_of_nothing(self):
        self.assertEqual(merkle.mth([]).hex(), hashlib.sha256(b"").hexdigest())

    def test_inclusion_for_every_leaf_and_size(self):
        for n in range(1, 34):
            ls = self.leaves(n)
            root = merkle.mth(ls)
            for m in range(n):
                path = merkle.inclusion_path(m, ls)
                self.assertTrue(merkle.verify_inclusion(ls[m], m, n, path, root), (m, n))

    def test_inclusion_fails_for_wrong_leaf_or_index(self):
        ls = self.leaves(13)
        root = merkle.mth(ls)
        path = merkle.inclusion_path(5, ls)
        self.assertFalse(merkle.verify_inclusion(ls[6], 5, 13, path, root))
        self.assertFalse(merkle.verify_inclusion(ls[5], 4, 13, path, root))
        # The tree size is authenticated by the signed tree head, so check a wrong root instead.
        self.assertFalse(merkle.verify_inclusion(ls[5], 5, 13, path, merkle.mth(ls[:12])))

    def test_consistency_for_every_pair(self):
        for n in range(1, 34):
            ls = self.leaves(n)
            for m in range(1, n + 1):
                proof = merkle.consistency_proof(m, ls)
                ok = merkle.verify_consistency(m, n, merkle.mth(ls[:m]), merkle.mth(ls), proof)
                self.assertTrue(ok, (m, n))

    def test_rewritten_history_fails_consistency(self):
        ls = self.leaves(20)
        old_root = merkle.mth(ls[:9])
        rewritten = list(ls)
        rewritten[3] = merkle.leaf_hash(b"forged")
        proof = merkle.consistency_proof(9, rewritten)
        self.assertFalse(merkle.verify_consistency(9, 20, old_root, merkle.mth(rewritten), proof))

    def test_log_class(self):
        log = merkle.MerkleLog()
        for i in range(10):
            log.append(f"e{i}".encode())
        r7 = log.root(7)
        self.assertTrue(merkle.verify_consistency(7, 10, r7, log.root(), log.consistency(7)))
        self.assertTrue(merkle.verify_inclusion(log.leaf(3), 3, 10, log.inclusion(3), log.root()))


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.ring = KeyRing()
        self.key = self.ring.create("SRO-TEST", "sub_registry", "2025-01-01")
        self.h = canonical.record_hash({"x": 1})

    def test_sign_and_verify(self):
        sig = self.ring.sign(self.key.key_id, deed_message(self.h))
        ok, _ = self.ring.verify(self.key.key_id, deed_message(self.h), sig, "2026-01-01")
        self.assertTrue(ok)

    def test_other_hash_fails(self):
        sig = self.ring.sign(self.key.key_id, deed_message(self.h))
        other = canonical.record_hash({"x": 2})
        ok, reason = self.ring.verify(self.key.key_id, deed_message(other), sig)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad signature")

    def test_revoked_key(self):
        sig = self.ring.sign(self.key.key_id, deed_message(self.h))
        self.ring.revoke(self.key.key_id, "2026-03-01")
        self.assertTrue(self.ring.verify(self.key.key_id, deed_message(self.h), sig, "2026-02-28")[0])
        self.assertFalse(self.ring.verify(self.key.key_id, deed_message(self.h), sig, "2026-03-01")[0])


if __name__ == "__main__":
    unittest.main()
