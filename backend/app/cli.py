"""Tiny command-line client for demos (standard library only).

    python -m app.cli verify --qr-file ../data/runtime/demo/qr.txt --document ../data/runtime/demo/deed_genuine.pdf
    python -m app.cli verify --deed SRO-NDP-2026-00001
    python -m app.cli flags --as-of 2026-10-10
"""

from __future__ import annotations

import argparse
import base64
import json
import urllib.error
import urllib.request

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
COLOUR = {"GENUINE_CURRENT": GREEN, "GENUINE_SUPERSEDED": YELLOW, "ALTERED": RED, "INVALID": RED}


def call(base: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(base.rstrip("/") + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def main() -> None:
    ap = argparse.ArgumentParser(description="Dolil Check demo client")
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--qr-file")
    v.add_argument("--qr")
    v.add_argument("--deed")
    v.add_argument("--document")
    f = sub.add_parser("flags")
    f.add_argument("--as-of", required=True)
    f.add_argument("--days", type=int, default=60)
    args = ap.parse_args()

    if args.cmd == "verify":
        body: dict = {}
        if args.qr_file:
            body["qr"] = open(args.qr_file, encoding="utf-8").read().strip()
        if args.qr:
            body["qr"] = args.qr
        if args.deed:
            body["deed_id"] = args.deed
        if args.document:
            body["document_b64"] = base64.b64encode(open(args.document, "rb").read()).decode()
        res = call(args.server, "POST", "/verify", body)
        if "verdict" not in res:
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return
        c = COLOUR.get(res["verdict"], "")
        print(f"\n{c}{res['verdict']}{RESET}  {res['message_bn']}\n{' ' * len(res['verdict'])}  {res['message_en']}\n")
        for chk in res["checks"]:
            mark = f"{GREEN}✓{RESET}" if chk["ok"] else f"{RED}✗{RESET}"
            print(f"  {mark} {chk['detail']}")
        if res.get("current_holders"):
            print("\n  Current holders of this plot:")
            for h in res["current_holders"]:
                print(f"    {h['party_id']}  {h['name']}  {h['area']} shotangsho")
        print()
    else:
        res = call(args.server, "GET", f"/flags?as_of={args.as_of}&days={args.days}")
        print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
