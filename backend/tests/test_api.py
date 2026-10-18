import base64
import os
import unittest

os.environ["DOLIL_NO_APP"] = "1"  # don't open the real runtime database on import

try:
    from starlette.testclient import TestClient  # needs starlette + httpx

    from app.main import create_app
except Exception:  # pragma: no cover
    TestClient = None

from app.registry import Registry

PLOT = {"mouza": "নদীপাড়া", "jl_no": "42", "survey": "BS", "dag_no": "7"}


@unittest.skipIf(TestClient is None, "pip install httpx to run API tests")
class ApiTests(unittest.TestCase):
    def setUp(self):
        reg = Registry()
        reg.ensure_office("SRO-NDP", "sub_registry")
        reg.ensure_office("ACL-NDP", "ac_land")
        self.c = TestClient(create_app(reg))
        r = self.c.post("/baselines", json={
            "office_id": "SRO-NDP", "date": "2025-01-01", "plot": PLOT, "khatian_no": "1", "total_area": "10",
            "holders": [{"party_id": "P-A", "name": "ক", "area": "10"}]})
        self.assertEqual(r.status_code, 201, r.text)
        self.doc = b"deed bytes"
        r = self.c.post("/deeds", json={
            "office_id": "SRO-NDP", "reg_date": "2026-01-01", "plot": PLOT, "khatian_no": "1",
            "sellers": [{"party_id": "P-A", "name": "ক", "area": "10"}],
            "buyers": [{"party_id": "P-B", "name": "খ", "area": "10"}], "consideration_bdt": 100,
            "document_b64": base64.b64encode(self.doc).decode()})
        self.assertEqual(r.status_code, 201, r.text)
        self.deed = r.json()

    def test_verify_genuine_and_altered(self):
        ok = self.c.post("/verify", json={"qr": self.deed["qr"],
                                          "document_b64": base64.b64encode(self.doc).decode()}).json()
        self.assertEqual(ok["verdict"], "GENUINE_CURRENT")
        bad = self.c.post("/verify", json={"qr": self.deed["qr"],
                                           "document_b64": base64.b64encode(b"deed bytez").decode()}).json()
        self.assertEqual(bad["verdict"], "ALTERED")

    def test_double_sale_returns_409(self):
        r = self.c.post("/deeds", json={
            "office_id": "SRO-NDP", "reg_date": "2026-02-01", "plot": PLOT, "khatian_no": "1",
            "sellers": [{"party_id": "P-A", "name": "ক", "area": "10"}],
            "buyers": [{"party_id": "P-C", "name": "গ", "area": "10"}], "consideration_bdt": 100})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"], "DOUBLE_SALE")

    def test_verify_accepts_the_phone_link(self):
        link = self.c.get(f"/deeds/{self.deed['deed_id']}/qr").json()["url"]
        self.assertIn("/v?q=DS1%7C", link)
        self.assertEqual(self.c.post("/verify", json={"qr": link}).json()["verdict"], "GENUINE_CURRENT")

    def test_pages_and_ui_endpoints(self):
        for path in ("/", "/register", "/mutation", "/guide", "/v", "/deed", "/static/app.js"):
            self.assertEqual(self.c.get(path).status_code, 200, path)
        self.assertEqual(len(self.c.get("/plots/all").json()), 1)
        self.assertEqual(self.c.get("/stats").json()["deeds"], 1)

    def test_public_brand_is_dolil_check(self):
        self.assertEqual(self.c.get("/api").json()["name"], "Dolil Check")
        dashboard = self.c.get("/").text
        certificate = self.c.get("/deed").text
        shared_js = self.c.get("/static/app.js").text
        self.assertIn("দলিল চেক", dashboard)
        self.assertIn("দলিল চেক", certificate)
        self.assertIn("দলিল চেক", shared_js)
        self.assertNotIn("Dolil Seal", dashboard + certificate + shared_js)

    def test_log_endpoints(self):
        sth = self.c.get("/log/sth").json()
        self.assertEqual(sth["tree_size"], 2)
        self.assertEqual(self.c.get("/log/inclusion?index=1").status_code, 200)
        self.assertEqual(self.c.get("/log/consistency?first=1").status_code, 200)
        self.assertEqual(self.c.get("/log/inclusion?index=9").status_code, 400)


if __name__ == "__main__":
    unittest.main()
