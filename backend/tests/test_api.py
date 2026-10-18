import base64
import os
import unittest
from unittest.mock import patch

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
        app = create_app(reg, admin_password="test-admin-password", session_secret="test-session-secret",
                         secure_cookies=False, public_url="https://dolil-check-demo.onrender.com")
        self.public = TestClient(app)
        self.c = TestClient(app)
        login = self.c.post("/admin/session", json={"password": "test-admin-password"})
        self.assertEqual(login.status_code, 200, login.text)
        self.admin_headers = {"X-CSRF-Token": login.json()["csrf"]}
        r = self.c.post("/baselines", json={
            "office_id": "SRO-NDP", "date": "2025-01-01", "plot": PLOT, "khatian_no": "1", "total_area": "10",
            "holders": [{"party_id": "P-A", "name": "ক", "area": "10"}]}, headers=self.admin_headers)
        self.assertEqual(r.status_code, 201, r.text)
        self.doc = b"deed bytes"
        r = self.c.post("/deeds", json={
            "office_id": "SRO-NDP", "reg_date": "2026-01-01", "plot": PLOT, "khatian_no": "1",
            "sellers": [{"party_id": "P-A", "name": "ক", "area": "10"}],
            "buyers": [{"party_id": "P-B", "name": "খ", "area": "10"}], "consideration_bdt": 100,
            "document_b64": base64.b64encode(self.doc).decode()}, headers=self.admin_headers)
        self.assertEqual(r.status_code, 201, r.text)
        self.deed = r.json()

    def test_verify_genuine_and_altered(self):
        # Verification stays public: this client has no administrator session.
        ok = self.public.post("/verify", json={"qr": self.deed["qr"],
                                               "document_b64": base64.b64encode(self.doc).decode()}).json()
        self.assertEqual(ok["verdict"], "GENUINE_CURRENT")
        bad = self.public.post("/verify", json={"qr": self.deed["qr"],
                                                "document_b64": base64.b64encode(b"deed bytez").decode()}).json()
        self.assertEqual(bad["verdict"], "ALTERED")

    def test_double_sale_returns_409(self):
        r = self.c.post("/deeds", json={
            "office_id": "SRO-NDP", "reg_date": "2026-02-01", "plot": PLOT, "khatian_no": "1",
            "sellers": [{"party_id": "P-A", "name": "ক", "area": "10"}],
            "buyers": [{"party_id": "P-C", "name": "গ", "area": "10"}], "consideration_bdt": 100},
            headers=self.admin_headers)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"], "DOUBLE_SALE")

    def test_verify_accepts_the_phone_link(self):
        link = self.c.get(f"/deeds/{self.deed['deed_id']}/qr").json()["url"]
        self.assertTrue(link.startswith("https://dolil-check-demo.onrender.com/v?q=DS1%7C"), link)
        self.assertNotIn("localhost", link)
        self.assertEqual(self.public.post("/verify", json={"qr": link}).json()["verdict"], "GENUINE_CURRENT")

    def test_render_external_url_is_used_for_public_qr(self):
        with patch.dict(os.environ, {"RENDER_EXTERNAL_URL": "https://dolil-check-live.onrender.com"}):
            app = create_app(self.c.app.state.registry, admin_password="x", session_secret="y",
                             secure_cookies=False)
            with TestClient(app) as render_client:
                link = render_client.get(f"/deeds/{self.deed['deed_id']}/qr").json()["url"]
        self.assertTrue(link.startswith("https://dolil-check-live.onrender.com/v?q=DS1%7C"), link)
        self.assertNotIn("localhost", link)

    def test_pages_and_ui_endpoints(self):
        for path in ("/", "/register", "/mutation", "/guide", "/v", "/deed", "/admin/login", "/static/app.js"):
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

    def test_anonymous_writes_are_denied(self):
        for path in ("/offices", "/baselines", "/deeds", "/mutations"):
            r = self.public.post(path, json={})
            self.assertEqual(r.status_code, 401, (path, r.text))
            self.assertEqual(r.json()["error"], "AUTH_REQUIRED")

    def test_authenticated_demo_write_and_csrf(self):
        no_csrf = self.c.post("/mutations", json={})
        self.assertEqual(no_csrf.status_code, 403)
        self.assertEqual(no_csrf.json()["error"], "CSRF_FAILED")

        ok = self.c.post("/mutations", headers=self.admin_headers, json={
            "office_id": "ACL-NDP", "deed_id": self.deed["deed_id"],
            "case_no": "DEMO-1", "date": "2026-02-01",
        })
        self.assertEqual(ok.status_code, 201, ok.text)

    def test_health_is_public_and_read_only(self):
        before = self.public.get("/stats").json()
        r = self.public.get("/health")
        after = self.public.get("/stats").json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["mode"], "competition-demo")
        self.assertEqual(before, after)

    def test_private_keys_are_not_served(self):
        self.assertEqual(self.public.get("/data/runtime/keys/private/example.pem").status_code, 404)
        keys = self.public.get("/keys").json()
        self.assertNotIn("private", str(keys).lower())


if __name__ == "__main__":
    unittest.main()
