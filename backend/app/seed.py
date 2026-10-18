"""Generate a fully synthetic registry, with planted fraud attempts.

    python -m app.seed            # writes data/runtime (refuses if it exists)
    python -m app.seed --reset    # wipes data/runtime first

Every name, mouza, plot and deed here is invented. No real person's data and no
government system is used (LandTech rulebook, section 8).
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import random
import shutil
from pathlib import Path

from .registry import Registry, Rejected, fmt_area

SRO, ACL = "SRO-NDP", "ACL-NDP"
MOUZAS = [("নদীপাড়া", "42"), ("শালবন", "57"), ("চরকান্দি", "63")]
# The demo story from the concept note (all names fictional): Rahim sells 10 shotangsho of
# Nodipara dag 123 to Karim, later tries to sell it again to Jabbar, a broker alters Karim's copy
# to 16 shotangsho, and Karim's mutation is still pending after 60 days.
STORY_DAG = 123
RAHIM = {"party_id": "P-RAHIM", "name": "রহিম উদ্দিন"}
KARIM = {"party_id": "P-KARIM", "name": "করিম মিয়া"}
JABBAR = {"party_id": "P-JABBAR", "name": "জব্বার আলী"}
STORY_DEED_DATE = "2026-07-20"   # more than 60 days before the seed's "today", so the mutation is overdue
FIRST = ["রহিম", "করিম", "সালমা", "জবা", "রফিক", "নাসরিন", "আনোয়ার", "মিনা", "হাবিব", "শিউলি", "তারেক",
         "রুমানা", "কামাল", "পারুল", "জসিম", "লাইলা", "মোস্তফা", "শাহানা", "বাবুল", "রেহানা"]
LAST = ["উদ্দিন", "মিয়া", "খাতুন", "রানী", "হোসেন", "বেগম", "আলী", "আক্তার", "সরকার", "মণ্ডল"]


def minimal_pdf(text: str) -> bytes:
    """A tiny valid one-page PDF (ASCII text) to act as the scanned deed."""
    stream = f"BT /F1 14 Tf 50 750 Td ({text}) Tj ET".encode("ascii")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def seed(data_dir: Path, n_plots_per_mouza: int = 40, n_deeds: int = 500, today: str = "2026-10-10") -> dict:
    rng = random.Random(2026)
    reg = Registry(str(data_dir / "dolil.db"), str(data_dir / "keys"))
    reg.ensure_office(SRO, "sub_registry")
    reg.ensure_office(ACL, "ac_land")

    people: dict[str, str] = {}

    def new_party() -> dict:
        pid = f"P-{len(people) + 1:05d}"
        people[pid] = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        return {"party_id": pid, "name": people[pid]}

    plots = []
    for mouza, jl in MOUZAS:
        # dag 123 is kept free for the scripted demo story below
        for dag in rng.sample([d for d in range(100, 1000) if d != STORY_DAG], n_plots_per_mouza):
            plot = {"mouza": mouza, "jl_no": jl, "survey": "BS", "dag_no": str(dag)}
            total = rng.randint(8, 60)
            holders, left = [], total
            for i in range(rng.randint(1, 3)):
                share = left if i == 2 or left <= 2 else rng.randint(1, left - 1)
                holders.append({**new_party(), "area": str(share)})
                left -= share
                if left == 0:
                    break
            res = reg.add_baseline({"office_id": SRO, "date": "2025-01-15", "plot": plot,
                                    "khatian_no": str(rng.randint(1, 900)), "total_area": str(total),
                                    "holders": holders})
            plots.append((plot, res["plot_id"]))

    start, end = dt.date(2025, 2, 1), dt.date.fromisoformat(today) - dt.timedelta(days=10)
    dates = sorted(start + dt.timedelta(days=rng.randint(0, (end - start).days)) for _ in range(n_deeds))
    deeds, mutated = [], 0
    for d in dates:
        plot, pid = rng.choice(plots)
        holders = reg.current_holders(pid)
        seller = rng.choice(holders)
        held_milli = int(round(float(seller["area"]) * 1000))
        sell_milli = held_milli if rng.random() < 0.5 or held_milli < 1000 else max(500, held_milli // 2 // 500 * 500)
        buyer = new_party() if rng.random() < 0.7 or len(people) < 5 else {
            "party_id": (pid_ := rng.choice(sorted(people))), "name": people[pid_]}
        if buyer["party_id"] == seller["party_id"]:
            continue
        res = reg.register_deed({
            "office_id": SRO, "reg_date": d.isoformat(), "plot": plot, "khatian_no": "1",
            "sellers": [{"party_id": seller["party_id"], "name": seller["name"], "area": fmt_area(sell_milli)}],
            "buyers": [{**buyer, "area": fmt_area(sell_milli)}],
            "consideration_bdt": sell_milli * rng.randint(80, 250)})
        deeds.append(res["deed_id"])
        m_date = d + dt.timedelta(days=rng.randint(7, 40))
        if rng.random() < 0.85 and m_date.isoformat() <= today:
            reg.add_mutation({"office_id": ACL, "deed_id": res["deed_id"], "case_no": f"{len(deeds)}/{d.year}",
                              "date": m_date.isoformat()})
            mutated += 1

    # ---------------- the demo story deed (with a document) and its altered copy
    demo_dir = data_dir / "demo"
    demo_dir.mkdir(exist_ok=True)
    mouza, jl = MOUZAS[0]
    story_plot = {"mouza": mouza, "jl_no": jl, "survey": "BS", "dag_no": str(STORY_DAG)}
    reg.add_baseline({"office_id": SRO, "date": "2025-01-15", "plot": story_plot, "khatian_no": "311",
                      "total_area": "24", "holders": [{**RAHIM, "area": "10"}, {**new_party(), "area": "14"}]})
    # The PDF stands in for the scanned paper deed; ASCII only because the tiny PDF uses a built-in font.
    text = f"Deed of sale | Mouza Nodipara JL {jl} dag {STORY_DAG} | Rahim Uddin to Karim Mia | area 10.000 decimal"
    genuine = minimal_pdf(text)
    altered = minimal_pdf(text.replace("area 10.000", "area 16.000"))  # the broker's edit, same length
    demo = reg.register_deed({
        "office_id": SRO, "reg_date": STORY_DEED_DATE, "plot": story_plot, "khatian_no": "311",
        "sellers": [{**RAHIM, "area": "10"}], "buyers": [{**KARIM, "area": "10"}], "consideration_bdt": 2500000,
        "document_b64": base64.b64encode(genuine).decode()})
    (demo_dir / "deed_genuine.pdf").write_bytes(genuine)
    (demo_dir / "deed_altered.pdf").write_bytes(altered)
    (demo_dir / "qr.txt").write_text(demo["qr"] + "\n", "utf-8")
    # No mutation is added for Karim's deed on purpose: it shows up as overdue on the AC Land dashboard.

    planted = []

    def attempt(label: str, fn):
        try:
            fn()
            planted.append({"case": label, "result": "ACCEPTED (unexpected!)"})
        except Rejected as e:
            planted.append({"case": label, "result": e.code, "message": e.message})

    attempt("Rahim sells the same land again, to Jabbar", lambda: reg.register_deed({
        "office_id": SRO, "reg_date": "2026-08-20", "plot": story_plot, "khatian_no": "311",
        "sellers": [{**RAHIM, "area": "10"}], "buyers": [{**JABBAR, "area": "10"}], "consideration_bdt": 2000000}))
    rich_plot, rich = max(((pl, h) for pl, p in plots for h in reg.current_holders(p)),
                          key=lambda ph: float(ph[1]["area"]))
    attempt("owner sells more than they hold", lambda: reg.register_deed({
        "office_id": SRO, "reg_date": today, "plot": rich_plot, "khatian_no": "1",
        "sellers": [{"party_id": rich["party_id"], "name": rich["name"], "area": f"{float(rich['area']) + 5:.3f}"}],
        "buyers": [{**new_party(), "area": f"{float(rich['area']) + 5:.3f}"}], "consideration_bdt": 900000}))
    attempt("stranger sells someone else's land", lambda: reg.register_deed({
        "office_id": SRO, "reg_date": today, "plot": plots[5][0], "khatian_no": "1",
        "sellers": [{**new_party(), "area": "2"}], "buyers": [{**new_party(), "area": "2"}],
        "consideration_bdt": 100000}))
    attempt("mutation for a deed that does not exist", lambda: reg.add_mutation({
        "office_id": ACL, "deed_id": "SRO-NDP-2026-09999", "case_no": "X-1", "date": today}))

    flags = reg.flags(today)
    summary = {
        "data_dir": str(data_dir), "plots": len(plots), "parties": len(people), "deeds": len(deeds) + 1,
        "mutations": mutated, "mutation_overdue": len(flags["mutation_overdue"]), "log_size": len(reg.log),
        "demo_deed": demo["deed_id"], "demo_qr_file": str(demo_dir / "qr.txt"), "planted_fraud": planted,
    }
    (demo_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), "utf-8")
    reg.close()
    return summary


def main() -> None:
    from .config import DATA_DIR

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="delete existing runtime data first")
    ap.add_argument("--deeds", type=int, default=500)
    args = ap.parse_args()
    if DATA_DIR.exists() and any(DATA_DIR.iterdir()):
        if not args.reset:
            raise SystemExit(f"{DATA_DIR} already has data; rerun with --reset to replace it")
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(json.dumps(seed(DATA_DIR, n_deeds=args.deeds), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
