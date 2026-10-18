"""HTTP API and web pages for Dolil Check (Starlette).

Run:  uvicorn app.main:app --reload      (from the backend/ folder)
Phone access on the same Wi-Fi:
      DOLIL_PUBLIC_URL=http://<your-laptop-ip>:8000 uvicorn app.main:app --host 0.0.0.0
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__
from .config import DATA_DIR, DEFAULT_OFFICES
from .registry import MUTATION_DEADLINE_DAYS, Registry, Rejected

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

STATUS = {
    "INVALID_INPUT": 400, "UNKNOWN_PLOT": 404, "UNKNOWN_DEED": 404, "UNKNOWN_OFFICE": 403,
    "WRONG_OFFICE": 403, "DOUBLE_SALE": 409, "OVER_SHARE": 409, "NOT_OWNER": 409,
    "ALREADY_BASELINED": 409, "ALREADY_MUTATED": 409,
}


def qr_text(value: str) -> str:
    """Accept the raw QR payload or the verify link a phone camera opens."""
    value = value.strip()
    if value.startswith(("http://", "https://")):
        q = parse_qs(urlparse(value).query).get("q")
        if q:
            return q[0]
    return value


def build_registry() -> Registry:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    reg = Registry(str(DATA_DIR / "dolil.db"), str(DATA_DIR / "keys"))
    for office, role in DEFAULT_OFFICES.items():
        reg.ensure_office(office, role)
    return reg


def create_app(registry: Registry | None = None) -> Starlette:
    reg = registry or build_registry()

    async def body(request: Request) -> dict:
        try:
            data = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise Rejected("INVALID_INPUT", "request body must be JSON")
        if not isinstance(data, dict):
            raise Rejected("INVALID_INPUT", "request body must be a JSON object")
        return data

    def int_param(request: Request, name: str, default: int | None = None) -> int | None:
        raw = request.query_params.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise Rejected("INVALID_INPUT", f"{name} must be an integer")

    def verify_link(request: Request, payload: str) -> str:
        base = os.environ.get("DOLIL_PUBLIC_URL") or str(request.base_url)
        return f"{base.rstrip('/')}/v?q={quote(payload, safe='')}"

    async def index(request: Request):
        return JSONResponse({
            "name": "Dolil Check", "version": __version__,
            "about": "Tamper-evident land deed registry: sealed deeds, public Merkle log, double-sale blocking.",
            "endpoints": [f"{', '.join(sorted(r.methods - {'HEAD'}))} {r.path}" for r in routes
                          if isinstance(r, Route)],
        })

    async def health(request: Request):
        return JSONResponse({"ok": True, "log_size": len(reg.log)})

    async def keys(request: Request):
        return JSONResponse(reg.public_keys())

    async def create_office(request: Request):
        b = await body(request)
        if b.get("role") not in ("sub_registry", "ac_land"):
            raise Rejected("INVALID_INPUT", "role must be sub_registry or ac_land")
        if not b.get("office_id"):
            raise Rejected("INVALID_INPUT", "office_id is required")
        return JSONResponse(reg.ensure_office(str(b["office_id"]), b["role"]), status_code=201)

    async def baselines(request: Request):
        return JSONResponse(reg.add_baseline(await body(request)), status_code=201)

    async def deeds(request: Request):
        return JSONResponse(reg.register_deed(await body(request)), status_code=201)

    async def deed(request: Request):
        rec = reg.record(request.path_params["deed_id"])
        if rec is None or rec["kind"] != "deed":
            raise Rejected("UNKNOWN_DEED", f"no deed {request.path_params['deed_id']}")
        return JSONResponse(rec)

    async def deed_qr(request: Request):
        payload = reg.qr_payload(request.path_params["deed_id"])
        return JSONResponse({"qr": payload, "url": verify_link(request, payload)})

    async def deed_qr_png(request: Request):
        payload = reg.qr_payload(request.path_params["deed_id"])
        try:
            import qrcode  # optional dependency
        except ImportError:
            return JSONResponse({"error": "QR_UNAVAILABLE", "message": "pip install qrcode[pil]", "qr": payload},
                                status_code=501)
        buf = io.BytesIO()
        qrcode.make(verify_link(request, payload), box_size=6, border=2).save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png")

    async def verify(request: Request):
        b = await body(request)
        doc = None
        if b.get("document_b64"):
            try:
                doc = base64.b64decode(b["document_b64"], validate=True)
            except (binascii.Error, ValueError):
                raise Rejected("INVALID_INPUT", "document_b64 is not valid base64")
        if not b.get("qr") and not b.get("deed_id"):
            raise Rejected("INVALID_INPUT", "send qr or deed_id")
        qr = qr_text(str(b["qr"])) if b.get("qr") else None
        deed_id = str(b["deed_id"]).strip() if b.get("deed_id") else None
        return JSONResponse(reg.verify(deed_id=deed_id, qr=qr, document=doc))

    async def mutations(request: Request):
        return JSONResponse(reg.add_mutation(await body(request)), status_code=201)

    async def flags(request: Request):
        as_of = request.query_params.get("as_of")
        if not as_of:
            raise Rejected("INVALID_INPUT", "as_of=YYYY-MM-DD is required")
        return JSONResponse(reg.flags(as_of, int_param(request, "days", MUTATION_DEADLINE_DAYS)))

    async def plot(request: Request):
        pid = request.query_params.get("plot_id", "")
        data = reg.plot(pid)
        if data is None:
            raise Rejected("UNKNOWN_PLOT", f"no plot {pid!r}")
        return JSONResponse(data)

    async def sth(request: Request):
        return JSONResponse(reg.sth(int_param(request, "size")))

    async def entries(request: Request):
        start = int_param(request, "start", 0)
        end = min(int_param(request, "end", start + 100), start + 1000)
        return JSONResponse(reg.entries(start, end))

    async def inclusion(request: Request):
        idx, size = int_param(request, "index"), int_param(request, "size")
        if idx is None or not 0 <= idx < len(reg.log) or (size is not None and not idx < size <= len(reg.log)):
            raise Rejected("INVALID_INPUT", "index/size out of range")
        return JSONResponse(reg.inclusion(idx, size))

    async def consistency(request: Request):
        first, second = int_param(request, "first"), int_param(request, "second")
        if first is None or not 0 < first <= (second or len(reg.log)) <= len(reg.log):
            raise Rejected("INVALID_INPUT", "first/second out of range")
        return JSONResponse(reg.consistency(first, second))

    async def all_plots(request: Request):
        return JSONResponse(reg.list_plots())

    async def stats(request: Request):
        return JSONResponse(reg.stats(request.query_params.get("as_of"), int_param(request, "days", MUTATION_DEADLINE_DAYS)))

    def page(name: str):
        async def handler(request: Request):
            return FileResponse(WEB_DIR / name)
        return handler

    async def rejections(request: Request):
        return JSONResponse(reg.rejections(int_param(request, "limit", 100)))

    async def on_rejected(request: Request, exc: Rejected):
        return JSONResponse(exc.as_dict(), status_code=STATUS.get(exc.code, 400))

    routes = [
        Route("/", page("index.html")),
        Route("/register", page("register.html")),
        Route("/v", page("verify.html")),
        Route("/deed", page("deed.html")),
        Route("/mutation", page("mutation.html")),
        Route("/guide", page("guide.html")),
        Route("/api", index),
        Route("/health", health),
        Route("/keys", keys),
        Route("/offices", create_office, methods=["POST"]),
        Route("/baselines", baselines, methods=["POST"]),
        Route("/deeds", deeds, methods=["POST"]),
        Route("/deeds/{deed_id}", deed),
        Route("/deeds/{deed_id}/qr", deed_qr),
        Route("/deeds/{deed_id}/qr.png", deed_qr_png),
        Route("/verify", verify, methods=["POST"]),
        Route("/mutations", mutations, methods=["POST"]),
        Route("/flags", flags),
        Route("/plots", plot),
        Route("/plots/all", all_plots),
        Route("/stats", stats),
        Route("/log/sth", sth),
        Route("/log/entries", entries),
        Route("/log/inclusion", inclusion),
        Route("/log/consistency", consistency),
        Route("/rejections", rejections),
        Mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static"),
    ]
    app = Starlette(
        routes=routes,
        exception_handlers={Rejected: on_rejected},
        middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
    )
    app.state.registry = reg
    return app


app = create_app() if os.environ.get("DOLIL_NO_APP") != "1" else None
