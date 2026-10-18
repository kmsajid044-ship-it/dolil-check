import tempfile
import unittest
from pathlib import Path

from app.registry import Registry
from app.runtime import initialize_runtime


class RuntimeInitializationTests(unittest.TestCase):
    def test_empty_runtime_is_initialized_and_verifies_consistently(self):
        with tempfile.TemporaryDirectory() as parent:
            data = Path(parent) / "runtime"
            self.assertTrue(initialize_runtime(data, n_deeds=8))

            reg = Registry(str(data / "dolil.db"), str(data / "keys"))
            qr = (data / "demo" / "qr.txt").read_text("utf-8").strip()
            genuine = reg.verify(qr=qr, document=(data / "demo" / "deed_genuine.pdf").read_bytes())
            altered = reg.verify(qr=qr, document=(data / "demo" / "deed_altered.pdf").read_bytes())
            reg.close()
            self.assertEqual(genuine["verdict"], "GENUINE_CURRENT")
            self.assertEqual(altered["verdict"], "ALTERED")

    def test_existing_runtime_is_validated_without_reseeding(self):
        with tempfile.TemporaryDirectory() as parent:
            data = Path(parent) / "runtime"
            self.assertTrue(initialize_runtime(data, n_deeds=8))
            qr_before = (data / "demo" / "qr.txt").read_bytes()
            db_before = (data / "dolil.db").read_bytes()

            self.assertFalse(initialize_runtime(data, n_deeds=8))
            self.assertEqual((data / "demo" / "qr.txt").read_bytes(), qr_before)
            self.assertEqual((data / "dolil.db").read_bytes(), db_before)

    def test_partial_runtime_fails_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as parent:
            data = Path(parent) / "runtime"
            data.mkdir()
            marker = data / "keep-me.txt"
            marker.write_text("partial", "utf-8")
            with self.assertRaisesRegex(RuntimeError, "partial"):
                initialize_runtime(data, n_deeds=1)
            self.assertEqual(marker.read_text("utf-8"), "partial")

    def test_corrupt_complete_runtime_fails_without_reseeding(self):
        with tempfile.TemporaryDirectory() as parent:
            data = Path(parent) / "runtime"
            self.assertTrue(initialize_runtime(data, n_deeds=8))
            qr = data / "demo" / "qr.txt"
            qr.write_text("DS1|corrupt", "utf-8")
            with self.assertRaisesRegex(RuntimeError, "do not verify|corrupt|inconsistent"):
                initialize_runtime(data, n_deeds=8)
            self.assertEqual(qr.read_text("utf-8"), "DS1|corrupt")


if __name__ == "__main__":
    unittest.main()
