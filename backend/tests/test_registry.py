import base64
import unittest

from app import merkle
from app.registry import Registry, Rejected

SRO = "SRO-NDP"  # invented sub-registry office
ACL = "ACL-NDP"  # invented AC Land office
PLOT = {"mouza": "নদীপাড়া", "jl_no": "৪২", "survey": "BS", "dag_no": "১২৩"}


def party(pid, name, area):
    return {"party_id": pid, "name": name, "area": area}


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.r = Registry()
        self.r.ensure_office(SRO, "sub_registry")
        self.r.ensure_office(ACL, "ac_land")
        self.r.add_baseline({
            "office_id": SRO, "date": "2025-01-10", "plot": PLOT, "khatian_no": "৭৭", "total_area": "33.000",
            "holders": [party("P-RAHIM", "রহিম উদ্দিন", "10"), party("P-SALMA", "সালমা খাতুন", "23")],
        })
        self.doc = b"%PDF-1.4 deed of sale, area 10.000 shotangsho"
        self.sale = self.r.register_deed(self.deed("2026-01-05", [party("P-RAHIM", "রহিম উদ্দিন", "10")],
                                                   [party("P-KARIM", "করিম মিয়া", "10")], doc=self.doc))

    def tearDown(self):
        self.r.close()

    def deed(self, date, sellers, buyers, doc=None, plot=PLOT):
        d = {"office_id": SRO, "reg_date": date, "plot": plot, "khatian_no": "৭৭", "sellers": sellers,
             "buyers": buyers, "consideration_bdt": 1500000}
        if doc is not None:
            d["document_b64"] = base64.b64encode(doc).decode()
        return d

    # --- the happy path
    def test_genuine_current(self):
        v = self.r.verify(qr=self.sale["qr"], document=self.doc)
        self.assertEqual(v["verdict"], "GENUINE_CURRENT", v["checks"])
        holders = {h["party_id"]: h["area"] for h in v["current_holders"]}
        self.assertEqual(holders, {"P-KARIM": "10.000", "P-SALMA": "23.000"})

    def test_same_plot_written_with_ascii_digits_is_the_same_plot(self):
        ascii_plot = {"mouza": "নদীপাড়া", "jl_no": "42", "survey": "BS", "dag_no": "123"}
        res = self.r.register_deed(self.deed("2026-02-01", [party("P-SALMA", "সালমা খাতুন", "3")],
                                             [party("P-JOBA", "জবা রানী", "3")], plot=ascii_plot))
        self.assertEqual(res["plot_id"], self.sale["plot_id"])

    # --- fraud cases
    def test_double_sale_is_blocked(self):
        with self.assertRaises(Rejected) as cm:
            self.r.register_deed(self.deed("2026-02-05", [party("P-RAHIM", "রহিম উদ্দিন", "10")],
                                           [party("P-JABBAR", "জব্বার আলী", "10")]))
        self.assertEqual(cm.exception.code, "DOUBLE_SALE")
        self.assertEqual(cm.exception.detail["earlier_sale"], self.sale["deed_id"])
        self.assertEqual(self.r.rejections()[0]["code"], "DOUBLE_SALE")

    def test_over_share_is_blocked(self):
        with self.assertRaises(Rejected) as cm:
            self.r.register_deed(self.deed("2026-02-05", [party("P-SALMA", "সালমা খাতুন", "30")],
                                           [party("P-JABBAR", "জব্বার আলী", "30")]))
        self.assertEqual(cm.exception.code, "OVER_SHARE")

    def test_stranger_cannot_sell(self):
        with self.assertRaises(Rejected) as cm:
            self.r.register_deed(self.deed("2026-02-05", [party("P-NOBODY", "অচেনা", "1")],
                                           [party("P-JABBAR", "জব্বার আলী", "1")]))
        self.assertEqual(cm.exception.code, "NOT_OWNER")

    def test_rejected_registration_leaves_no_trace_in_log(self):
        size = len(self.r.log)
        with self.assertRaises(Rejected):
            self.r.register_deed(self.deed("2026-02-05", [party("P-RAHIM", "রহিম উদ্দিন", "10")],
                                           [party("P-JABBAR", "জব্বার আলী", "10")]))
        self.assertEqual(len(self.r.log), size)
        self.assertEqual(self.r.sth()["tree_size"], size)

    def test_altered_document(self):
        altered = self.doc.replace(b"10.000", b"16.000")
        v = self.r.verify(qr=self.sale["qr"], document=altered)
        self.assertEqual(v["verdict"], "ALTERED")

    def test_forged_qr(self):
        parts = self.sale["qr"].split("|")
        parts[4] = "0" * 64  # pretend to be a different record
        v = self.r.verify(qr="|".join(parts))
        self.assertEqual(v["verdict"], "INVALID")

    def test_unknown_deed(self):
        self.assertEqual(self.r.verify(deed_id="SRO-NDP-2026-99999")["verdict"], "INVALID")

    def test_resold_land_shows_superseded(self):
        self.r.register_deed(self.deed("2026-03-01", [party("P-KARIM", "করিম মিয়া", "4")],
                                       [party("P-JOBA", "জবা রানী", "4")]))
        v = self.r.verify(deed_id=self.sale["deed_id"])
        self.assertEqual(v["verdict"], "GENUINE_SUPERSEDED")
        self.assertEqual(len(v["later_transfers_by_buyers"]), 1)

    def test_database_tampering_is_detected(self):
        row = self.r.conn.execute("SELECT record_json FROM records WHERE record_id=?",
                                  (self.sale["deed_id"],)).fetchone()
        forged = row["record_json"].replace('"area_milli":10000', '"area_milli":16000')
        self.assertNotEqual(forged, row["record_json"])
        self.r.conn.execute("UPDATE records SET record_json=? WHERE record_id=?", (forged, self.sale["deed_id"]))
        v = self.r.verify(deed_id=self.sale["deed_id"])
        self.assertEqual(v["verdict"], "INVALID")
        self.assertFalse(next(c for c in v["checks"] if c["check"] == "record_intact")["ok"])

    # --- mutation link
    def test_mutation_flags(self):
        flags = self.r.flags(as_of="2026-03-15", days=45)
        self.assertEqual([f["deed_id"] for f in flags["mutation_overdue"]], [self.sale["deed_id"]])
        self.r.add_mutation({"office_id": ACL, "deed_id": self.sale["deed_id"], "case_no": "১০১/২০২৬",
                             "date": "2026-03-20"})
        self.assertEqual(self.r.flags(as_of="2026-03-25")["mutation_overdue"], [])
        self.assertEqual(self.r.verify(deed_id=self.sale["deed_id"])["mutation"]["date"], "2026-03-20")

    def test_mutation_without_deed_is_refused(self):
        with self.assertRaises(Rejected) as cm:
            self.r.add_mutation({"office_id": ACL, "deed_id": "SRO-NDP-2026-04040", "case_no": "9",
                                 "date": "2026-03-20"})
        self.assertEqual(cm.exception.code, "UNKNOWN_DEED")

    def test_sub_registry_cannot_sign_mutations(self):
        with self.assertRaises(Rejected) as cm:
            self.r.add_mutation({"office_id": SRO, "deed_id": self.sale["deed_id"], "case_no": "9",
                                 "date": "2026-03-20"})
        self.assertEqual(cm.exception.code, "WRONG_OFFICE")

    # --- the public log
    def test_log_heads_are_consistent(self):
        first = self.r.sth()
        self.r.register_deed(self.deed("2026-03-01", [party("P-SALMA", "সালমা খাতুন", "5")],
                                       [party("P-JOBA", "জবা রানী", "5")]))
        second = self.r.sth()
        c = self.r.consistency(first["tree_size"], second["tree_size"])
        self.assertTrue(merkle.verify_consistency(
            first["tree_size"], second["tree_size"], bytes.fromhex(first["root_hex"]),
            bytes.fromhex(second["root_hex"]), [bytes.fromhex(h) for h in c["proof"]]))

    def test_persistence(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            db, keys = os.path.join(tmp, "r.db"), os.path.join(tmp, "keys")
            r1 = Registry(db, keys)
            r1.ensure_office(SRO, "sub_registry")
            r1.add_baseline({"office_id": SRO, "date": "2025-01-10", "plot": PLOT, "khatian_no": "1",
                             "total_area": "5", "holders": [party("P-A", "ক", "5")]})
            res = r1.register_deed(self.deed("2026-01-01", [party("P-A", "ক", "5")], [party("P-B", "খ", "5")]))
            r1.conn.close()
            r2 = Registry(db, keys)
            self.assertEqual(r2.verify(qr=res["qr"])["verdict"], "GENUINE_CURRENT")
            r2.close()


if __name__ == "__main__":
    unittest.main()
