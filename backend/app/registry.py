"""The registry: seals deeds, keeps the share ledger, links mutations, verifies.

Everything that changes ownership goes through here, inside one database
transaction, and every accepted change becomes a signed entry in the
append-only Merkle log.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import sqlite3
import threading
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import canonical, merkle
from .signing import (
    KeyRing,
    baseline_message,
    deed_message,
    mutation_message,
    sth_message,
    verify_with_listing,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS leaves (
    idx        INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,
    ref        TEXT NOT NULL,
    entry      BLOB NOT NULL,
    leaf_hash  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sth (
    tree_size  INTEGER PRIMARY KEY,
    root_hex   TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    key_id     TEXT NOT NULL,
    signature  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plots (
    plot_id     TEXT PRIMARY KEY,
    mouza       TEXT NOT NULL,
    jl_no       TEXT NOT NULL,
    survey      TEXT NOT NULL,
    dag_no      TEXT NOT NULL,
    total_milli INTEGER NOT NULL,
    baseline_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    record_id   TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,           -- baseline | deed | mutation
    record_json TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    key_id      TEXT NOT NULL,
    signature   TEXT NOT NULL,
    leaf_index  INTEGER NOT NULL,
    signed_on   TEXT NOT NULL,
    plot_id     TEXT,
    deed_id     TEXT                     -- for mutations: the deed they belong to
);
CREATE TABLE IF NOT EXISTS parties (
    record_id   TEXT NOT NULL,
    plot_id     TEXT NOT NULL,
    party_id    TEXT NOT NULL,
    side        TEXT NOT NULL,           -- seller | buyer | holder
    area_milli  INTEGER NOT NULL,
    leaf_index  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS parties_plot ON parties(plot_id, party_id);
CREATE TABLE IF NOT EXISTS holdings (
    plot_id     TEXT NOT NULL,
    party_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    area_milli  INTEGER NOT NULL,
    last_leaf   INTEGER NOT NULL,
    PRIMARY KEY (plot_id, party_id)
);
CREATE TABLE IF NOT EXISTS rejections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    code        TEXT NOT NULL,
    message     TEXT NOT NULL,
    payload     TEXT NOT NULL
);
"""

QR_PREFIX = "DS1"


class Rejected(Exception):
    """A request the registry refuses. `code` is stable and machine-readable."""

    def __init__(self, code: str, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def as_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "detail": self.detail}


# ---------------------------------------------------------------- helpers

def parse_area(value: Any) -> int:
    """Area in shotangsho (decimal) -> integer thousandths. Never floats."""
    if isinstance(value, bool):
        raise Rejected("INVALID_INPUT", "area must be a number of shotangsho, e.g. \"10.5\"")
    if isinstance(value, int):
        milli = value * 1000
    else:
        try:
            d = Decimal(canonical.norm_text(str(value)))
        except InvalidOperation:
            raise Rejected("INVALID_INPUT", f"area {value!r} is not a number")
        if d != d.quantize(Decimal("0.001")):
            raise Rejected("INVALID_INPUT", "area can have at most 3 decimal places")
        milli = int(d * 1000)
    if milli <= 0:
        raise Rejected("INVALID_INPUT", "area must be greater than zero")
    return milli


def fmt_area(milli: int) -> str:
    return f"{Decimal(milli) / 1000:.3f}"


def parse_date(value: Any, field: str) -> str:
    try:
        return dt.date.fromisoformat(canonical.norm_text(str(value))).isoformat()
    except ValueError:
        raise Rejected("INVALID_INPUT", f"{field} must be a date like 2026-10-10")


def make_plot_id(mouza: str, jl_no: str, survey: str, dag_no: str) -> str:
    parts = [canonical.norm_text(str(p)) for p in (mouza, jl_no, survey, dag_no)]
    if not all(parts):
        raise Rejected("INVALID_INPUT", "plot needs mouza, jl_no, survey and dag_no")
    return "{}|JL {}|{}|dag {}".format(*parts)


def _require(obj: dict, *fields: str) -> None:
    missing = [f for f in fields if obj.get(f) in (None, "", [])]
    if missing:
        raise Rejected("INVALID_INPUT", "missing field(s): " + ", ".join(missing))


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- registry

# Example deadline for a deed to get its mutation; the real limit must be set with mentors/the AC Land office.
MUTATION_DEADLINE_DAYS = 60


class Registry:
    LOG_OFFICE = "LOG"

    def __init__(self, db_path: str = ":memory:", keys_dir: Optional[str] = None):
        self.conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()
        self.keys = KeyRing.load(keys_dir)
        self.log = merkle.MerkleLog(
            bytes.fromhex(r["leaf_hash"]) for r in self.conn.execute("SELECT leaf_hash FROM leaves ORDER BY idx")
        )
        self.ensure_office(self.LOG_OFFICE, "log")

    # ------------------------------------------------------------ offices
    def ensure_office(self, office_id: str, role: str, valid_from: str = "2000-01-01") -> dict:
        try:
            info = self.keys.active_key(office_id)
        except KeyError:
            info = self.keys.create(office_id, role, valid_from)
        return {"office_id": office_id, "key_id": info.key_id, "role": info.role}

    def _office_key(self, office_id: str, role: str):
        try:
            info = self.keys.active_key(office_id)
        except KeyError:
            raise Rejected("UNKNOWN_OFFICE", f"office {office_id!r} has no signing key")
        if info.role != role:
            raise Rejected("WRONG_OFFICE", f"office {office_id!r} is a {info.role} office, not {role}")
        return info

    # ------------------------------------------------------------ log internals
    def _append(self, kind: str, ref: str, entry: dict) -> int:
        """Append inside the caller's transaction and publish a new signed tree head."""
        data = canonical.canonical_bytes(entry)
        idx = self.log.append(data)  # rolled back by _transaction if anything later fails
        self.conn.execute(
            "INSERT INTO leaves(idx, kind, ref, entry, leaf_hash) VALUES (?,?,?,?,?)",
            (idx, kind, ref, data, self.log.leaf(idx).hex()),
        )
        self._publish_sth()
        return idx

    def _publish_sth(self) -> None:
        size = len(self.log)
        root = self.log.root().hex()
        ts = _now()
        key = self.keys.active_key(self.LOG_OFFICE)
        sig = self.keys.sign(key.key_id, sth_message(size, root, ts))
        self.conn.execute(
            "INSERT OR REPLACE INTO sth(tree_size, root_hex, timestamp, key_id, signature) VALUES (?,?,?,?,?)",
            (size, root, ts, key.key_id, sig),
        )

    def _seal(self, kind: str, record_id: str, record: dict, office_key, message_fn, signed_on: str,
              plot_id: Optional[str], deed_id: Optional[str] = None) -> dict:
        rhash = canonical.record_hash(record)
        sig = self.keys.sign(office_key.key_id, message_fn(rhash))
        entry = {"kind": kind, "ref": record_id, "record_hash": rhash, "key_id": office_key.key_id,
                 "sig": sig, "signed_on": signed_on}
        idx = self._append(kind, record_id, entry)
        self.conn.execute(
            "INSERT INTO records(record_id, kind, record_json, record_hash, key_id, signature, leaf_index,"
            " signed_on, plot_id, deed_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (record_id, kind, canonical.canonical_bytes(record).decode("utf-8"), rhash, office_key.key_id,
             sig, idx, signed_on, plot_id, deed_id),
        )
        return {"record_hash": rhash, "key_id": office_key.key_id, "signature": sig, "leaf_index": idx}

    def _reject(self, kind: str, err: Rejected, payload: dict) -> None:
        safe = {k: v for k, v in payload.items() if k not in ("document_b64",)}
        self.conn.execute(
            "INSERT INTO rejections(at, kind, code, message, payload) VALUES (?,?,?,?,?)",
            (_now(), kind, err.code, err.message, json.dumps(safe, ensure_ascii=False, default=str)),
        )

    def _transaction(self, kind: str, payload: dict, fn):
        with self.lock:
            size_before = len(self.log)
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                result = fn()
            except Rejected as err:
                self.conn.execute("ROLLBACK")
                del self.log._leaves[size_before:]
                self._reject(kind, err, payload)
                raise
            except Exception:
                self.conn.execute("ROLLBACK")
                del self.log._leaves[size_before:]
                raise
            self.conn.execute("COMMIT")
            return result

    # ------------------------------------------------------------ baseline (back-fill of current holders)
    def add_baseline(self, payload: dict) -> dict:
        """Seal a plot's current, office-verified holders. This is how existing land enters the system."""
        return self._transaction("baseline", payload, lambda: self._add_baseline(payload))

    def _add_baseline(self, p: dict) -> dict:
        _require(p, "office_id", "date", "plot", "khatian_no", "holders", "total_area")
        key = self._office_key(p["office_id"], "sub_registry")
        date = parse_date(p["date"], "date")
        plot = p["plot"]
        _require(plot, "mouza", "jl_no", "survey", "dag_no")
        plot_id = make_plot_id(plot["mouza"], plot["jl_no"], plot["survey"], plot["dag_no"])
        if self.conn.execute("SELECT 1 FROM plots WHERE plot_id=?", (plot_id,)).fetchone():
            raise Rejected("ALREADY_BASELINED", f"plot {plot_id} already has a baseline record")
        total = parse_area(p["total_area"])
        holders = self._parties(p["holders"], "holders")
        if sum(h["area_milli"] for h in holders) > total:
            raise Rejected("OVER_SHARE", "holders' shares add up to more than the plot's area")
        baseline_id = f"BL-{canonical.sha256_hex(plot_id.encode())[:10]}"
        record = {
            "type": "baseline", "v": 1, "baseline_id": baseline_id, "office_id": p["office_id"], "date": date,
            "plot_id": plot_id, "mouza": plot["mouza"], "jl_no": str(plot["jl_no"]), "survey": plot["survey"],
            "dag_no": str(plot["dag_no"]), "khatian_no": str(p["khatian_no"]), "total_milli": total,
            "holders": holders,
        }
        sealed = self._seal("baseline", baseline_id, record, key, baseline_message, date, plot_id)
        self.conn.execute(
            "INSERT INTO plots(plot_id, mouza, jl_no, survey, dag_no, total_milli, baseline_id) VALUES (?,?,?,?,?,?,?)",
            (plot_id, canonical.norm_text(plot["mouza"]), canonical.norm_text(str(plot["jl_no"])),
             canonical.norm_text(plot["survey"]), canonical.norm_text(str(plot["dag_no"])), total, baseline_id),
        )
        for h in holders:
            self._credit(plot_id, h, sealed["leaf_index"])
            self._party_row(baseline_id, plot_id, h, "holder", sealed["leaf_index"])
        return {"baseline_id": baseline_id, "plot_id": plot_id, **sealed}

    # ------------------------------------------------------------ deeds
    def register_deed(self, payload: dict) -> dict:
        return self._transaction("deed", payload, lambda: self._register_deed(payload))

    def _register_deed(self, p: dict) -> dict:
        _require(p, "office_id", "reg_date", "plot", "khatian_no", "sellers", "buyers", "consideration_bdt")
        key = self._office_key(p["office_id"], "sub_registry")
        reg_date = parse_date(p["reg_date"], "reg_date")
        plot = p["plot"]
        _require(plot, "mouza", "jl_no", "survey", "dag_no")
        plot_id = make_plot_id(plot["mouza"], plot["jl_no"], plot["survey"], plot["dag_no"])
        if not self.conn.execute("SELECT 1 FROM plots WHERE plot_id=?", (plot_id,)).fetchone():
            raise Rejected("UNKNOWN_PLOT", f"plot {plot_id} is not in the registry (no baseline record)")
        sellers = self._parties(p["sellers"], "sellers")
        buyers = self._parties(p["buyers"], "buyers")
        if sum(s["area_milli"] for s in sellers) != sum(b["area_milli"] for b in buyers):
            raise Rejected("INVALID_INPUT", "area sold must equal area bought")
        overlap = {s["party_id"] for s in sellers} & {b["party_id"] for b in buyers}
        if overlap:
            raise Rejected("INVALID_INPUT", "a party cannot be both seller and buyer: " + ", ".join(sorted(overlap)))
        try:
            consideration = int(p["consideration_bdt"])
        except (TypeError, ValueError):
            raise Rejected("INVALID_INPUT", "consideration_bdt must be a whole number of taka")

        prev: List[int] = []
        for s in sellers:
            self._check_seller(plot_id, s)
            row = self.conn.execute(
                "SELECT last_leaf FROM holdings WHERE plot_id=? AND party_id=?", (plot_id, s["party_id"])
            ).fetchone()
            prev.append(row["last_leaf"])

        doc_sha256 = None
        if p.get("document_b64"):
            try:
                doc_sha256 = canonical.sha256_hex(base64.b64decode(p["document_b64"], validate=True))
            except ValueError:
                raise Rejected("INVALID_INPUT", "document_b64 is not valid base64")
        elif p.get("document_sha256"):
            doc_sha256 = str(p["document_sha256"]).lower()

        year = reg_date[:4]
        n = self.conn.execute(
            "SELECT COUNT(*) FROM records WHERE kind='deed' AND record_id LIKE ?", (f"{p['office_id']}-{year}-%",)
        ).fetchone()[0]
        deed_id = f"{p['office_id']}-{year}-{n + 1:05d}"
        record = {
            "type": "deed", "v": 1, "deed_id": deed_id, "office_id": p["office_id"], "reg_date": reg_date,
            "plot_id": plot_id, "mouza": plot["mouza"], "jl_no": str(plot["jl_no"]), "survey": plot["survey"],
            "dag_no": str(plot["dag_no"]), "khatian_no": str(p["khatian_no"]), "sellers": sellers,
            "buyers": buyers, "consideration_bdt": consideration, "doc_sha256": doc_sha256,
            "prev": sorted(set(prev)),
        }
        sealed = self._seal("deed", deed_id, record, key, deed_message, reg_date, plot_id)
        for s in sellers:
            self._debit(plot_id, s)
            self._party_row(deed_id, plot_id, s, "seller", sealed["leaf_index"])
        for b in buyers:
            self._credit(plot_id, b, sealed["leaf_index"])
            self._party_row(deed_id, plot_id, b, "buyer", sealed["leaf_index"])
        return {"deed_id": deed_id, "plot_id": plot_id, "doc_sha256": doc_sha256, **sealed,
                "qr": self.qr_payload(deed_id)}

    def _check_seller(self, plot_id: str, s: dict) -> None:
        row = self.conn.execute(
            "SELECT area_milli FROM holdings WHERE plot_id=? AND party_id=?", (plot_id, s["party_id"])
        ).fetchone()
        held = row["area_milli"] if row else 0
        if held >= s["area_milli"]:
            return
        if row is None:
            raise Rejected("NOT_OWNER", f"{s['party_id']} has never held any share of {plot_id}",
                           {"party_id": s["party_id"], "plot_id": plot_id})
        sold = self.conn.execute(
            "SELECT record_id, leaf_index FROM parties WHERE plot_id=? AND party_id=? AND side='seller'"
            " ORDER BY leaf_index DESC LIMIT 1", (plot_id, s["party_id"])
        ).fetchone()
        holders = self.current_holders(plot_id)
        detail = {"party_id": s["party_id"], "plot_id": plot_id, "holds": fmt_area(held),
                  "tried_to_sell": fmt_area(s["area_milli"]), "current_holders": holders,
                  "earlier_sale": sold["record_id"] if sold else None}
        if held == 0 and sold:
            raise Rejected("DOUBLE_SALE",
                           f"{s['party_id']} already sold this land by deed {sold['record_id']}; "
                           "they own nothing in this plot now", detail)
        raise Rejected("OVER_SHARE",
                       f"{s['party_id']} holds {fmt_area(held)} shotangsho but tried to sell "
                       f"{fmt_area(s['area_milli'])}", detail)

    # ------------------------------------------------------------ mutations
    def add_mutation(self, payload: dict) -> dict:
        return self._transaction("mutation", payload, lambda: self._add_mutation(payload))

    def _add_mutation(self, p: dict) -> dict:
        _require(p, "office_id", "deed_id", "case_no", "date")
        key = self._office_key(p["office_id"], "ac_land")
        date = parse_date(p["date"], "date")
        deed = self._record(p["deed_id"], "deed")
        if deed is None:
            raise Rejected("UNKNOWN_DEED", f"no deed {p['deed_id']} in the registry; mutation refused")
        if date < deed["signed_on"]:
            raise Rejected("INVALID_INPUT", "mutation date is before the deed's registration date")
        if self.conn.execute("SELECT 1 FROM records WHERE kind='mutation' AND deed_id=?", (p["deed_id"],)).fetchone():
            raise Rejected("ALREADY_MUTATED", f"deed {p['deed_id']} already has a mutation")
        mutation_id = f"{p['office_id']}-{canonical.norm_text(str(p['case_no']))}"
        if self._record(mutation_id, "mutation"):
            raise Rejected("INVALID_INPUT", f"mutation case {mutation_id} already exists")
        drec = json.loads(deed["record_json"])
        record = {"type": "mutation", "v": 1, "mutation_id": mutation_id, "office_id": p["office_id"],
                  "deed_id": p["deed_id"], "deed_record_hash": deed["record_hash"], "case_no": str(p["case_no"]),
                  "date": date, "plot_id": drec["plot_id"],
                  "new_holders": [b["party_id"] for b in drec["buyers"]]}
        sealed = self._seal("mutation", mutation_id, record, key, mutation_message, date, drec["plot_id"],
                            deed_id=p["deed_id"])
        return {"mutation_id": mutation_id, **sealed}

    def flags(self, as_of: str, days: int = MUTATION_DEADLINE_DAYS) -> dict:
        as_of = parse_date(as_of, "as_of")
        cutoff = (dt.date.fromisoformat(as_of) - dt.timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            "SELECT d.record_id, d.signed_on, d.plot_id FROM records d WHERE d.kind='deed' AND d.signed_on <= ?"
            " AND NOT EXISTS (SELECT 1 FROM records m WHERE m.kind='mutation' AND m.deed_id=d.record_id)"
            " ORDER BY d.signed_on", (cutoff,)
        ).fetchall()
        pending = [{"deed_id": r["record_id"], "reg_date": r["signed_on"], "plot_id": r["plot_id"],
                    "days_pending": (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(r["signed_on"])).days}
                   for r in rows]
        refused = [dict(r) for r in self.conn.execute(
            "SELECT at, kind, code, message FROM rejections WHERE kind='mutation' ORDER BY id DESC LIMIT 50")]
        return {"as_of": as_of, "threshold_days": days, "mutation_overdue": pending, "refused_mutations": refused}

    # ------------------------------------------------------------ ledger internals
    def _parties(self, items: Iterable[dict], label: str) -> List[dict]:
        out, seen = [], set()
        if not isinstance(items, list) or not items:
            raise Rejected("INVALID_INPUT", f"{label} must be a non-empty list")
        for it in items:
            if not isinstance(it, dict):
                raise Rejected("INVALID_INPUT", f"each of {label} must be an object")
            _require(it, "party_id", "name", "area")
            pid = canonical.norm_text(str(it["party_id"]))
            if pid in seen:
                raise Rejected("INVALID_INPUT", f"{pid} appears twice in {label}")
            seen.add(pid)
            out.append({"party_id": pid, "name": canonical.norm_text(str(it["name"])),
                        "area_milli": parse_area(it["area"])})
        return sorted(out, key=lambda x: x["party_id"])

    def _credit(self, plot_id: str, party: dict, leaf: int) -> None:
        self.conn.execute(
            "INSERT INTO holdings(plot_id, party_id, name, area_milli, last_leaf) VALUES (?,?,?,?,?)"
            " ON CONFLICT(plot_id, party_id) DO UPDATE SET area_milli = area_milli + excluded.area_milli,"
            " last_leaf = excluded.last_leaf, name = excluded.name",
            (plot_id, party["party_id"], party["name"], party["area_milli"], leaf),
        )

    def _debit(self, plot_id: str, party: dict) -> None:
        self.conn.execute(
            "UPDATE holdings SET area_milli = area_milli - ? WHERE plot_id=? AND party_id=?",
            (party["area_milli"], plot_id, party["party_id"]),
        )

    def _party_row(self, record_id: str, plot_id: str, party: dict, side: str, leaf: int) -> None:
        self.conn.execute(
            "INSERT INTO parties(record_id, plot_id, party_id, side, area_milli, leaf_index) VALUES (?,?,?,?,?,?)",
            (record_id, plot_id, party["party_id"], side, party["area_milli"], leaf),
        )

    def _record(self, record_id: str, kind: Optional[str] = None):
        q = "SELECT * FROM records WHERE record_id=?" + (" AND kind=?" if kind else "")
        return self.conn.execute(q, (record_id, kind) if kind else (record_id,)).fetchone()

    # ------------------------------------------------------------ reads
    def current_holders(self, plot_id: str) -> List[dict]:
        return [{"party_id": r["party_id"], "name": r["name"], "area": fmt_area(r["area_milli"])}
                for r in self.conn.execute(
                    "SELECT party_id, name, area_milli FROM holdings WHERE plot_id=? AND area_milli>0"
                    " ORDER BY party_id", (plot_id,))]

    def plot(self, plot_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM plots WHERE plot_id=?", (plot_id,)).fetchone()
        if row is None:
            return None
        history = [dict(r) for r in self.conn.execute(
            "SELECT record_id, kind, signed_on, leaf_index FROM records WHERE plot_id=? ORDER BY leaf_index",
            (plot_id,))]
        return {"plot_id": plot_id, "mouza": row["mouza"], "jl_no": row["jl_no"], "survey": row["survey"],
                "dag_no": row["dag_no"], "total_area": fmt_area(row["total_milli"]),
                "current_holders": self.current_holders(plot_id), "history": history}

    def list_plots(self) -> List[dict]:
        return [{"plot_id": r["plot_id"], "mouza": r["mouza"], "jl_no": r["jl_no"], "survey": r["survey"],
                 "dag_no": r["dag_no"], "total_area": fmt_area(r["total_milli"])}
                for r in self.conn.execute(
                    "SELECT * FROM plots ORDER BY mouza, CAST(dag_no AS INTEGER), dag_no")]

    def stats(self, as_of: Optional[str] = None, days: int = MUTATION_DEADLINE_DAYS) -> dict:
        count = lambda q: self.conn.execute(q).fetchone()[0]  # noqa: E731
        as_of = as_of or dt.date.today().isoformat()
        by_code = {r["code"]: r["n"] for r in self.conn.execute(
            "SELECT code, COUNT(*) AS n FROM rejections WHERE code != 'INVALID_INPUT' GROUP BY code")}
        return {
            "plots": count("SELECT COUNT(*) FROM plots"),
            "deeds": count("SELECT COUNT(*) FROM records WHERE kind='deed'"),
            "mutations": count("SELECT COUNT(*) FROM records WHERE kind='mutation'"),
            "log_size": len(self.log),
            "blocked": sum(by_code.values()),
            "blocked_by_code": by_code,
            "mutation_overdue": len(self.flags(as_of, days)["mutation_overdue"]),
            "as_of": as_of,
        }

    def record(self, record_id: str) -> Optional[dict]:
        row = self._record(record_id)
        if row is None:
            return None
        sth = self.sth()
        return {"record_id": record_id, "kind": row["kind"], "record": json.loads(row["record_json"]),
                "record_hash": row["record_hash"], "key_id": row["key_id"], "signature": row["signature"],
                "leaf_index": row["leaf_index"], "sth": sth,
                "inclusion_proof": [h.hex() for h in self.log.inclusion(row["leaf_index"], sth["tree_size"])]}

    def qr_payload(self, deed_id: str) -> str:
        row = self._record(deed_id, "deed")
        if row is None:
            raise Rejected("UNKNOWN_DEED", f"no deed {deed_id}")
        return "|".join([QR_PREFIX, deed_id, str(row["leaf_index"]), row["key_id"], row["record_hash"],
                         row["signature"]])

    def rejections(self, limit: int = 100) -> List[dict]:
        out = []
        for r in self.conn.execute("SELECT * FROM rejections ORDER BY id DESC LIMIT ?", (limit,)):
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    # ------------------------------------------------------------ log API
    def sth(self, size: Optional[int] = None) -> dict:
        q = "SELECT * FROM sth " + ("WHERE tree_size=?" if size else "ORDER BY tree_size DESC LIMIT 1")
        row = self.conn.execute(q, (size,) if size else ()).fetchone()
        if row is None:
            return {"tree_size": 0, "root_hex": merkle.EMPTY_ROOT.hex(), "timestamp": None, "key_id": None,
                    "signature": None}
        return dict(row)

    def entries(self, start: int, end: int) -> List[dict]:
        return [{"index": r["idx"], "kind": r["kind"], "ref": r["ref"], "entry": bytes(r["entry"]).decode("utf-8"),
                 "leaf_hash": r["leaf_hash"]}
                for r in self.conn.execute("SELECT * FROM leaves WHERE idx>=? AND idx<? ORDER BY idx", (start, end))]

    def inclusion(self, index: int, size: Optional[int] = None) -> dict:
        size = size or len(self.log)
        return {"index": index, "tree_size": size, "leaf_hash": self.log.leaf(index).hex(),
                "path": [h.hex() for h in self.log.inclusion(index, size)], "root_hex": self.log.root(size).hex()}

    def consistency(self, first: int, second: Optional[int] = None) -> dict:
        second = second or len(self.log)
        return {"first": first, "second": second, "proof": [h.hex() for h in self.log.consistency(first, second)],
                "first_root": self.log.root(first).hex(), "second_root": self.log.root(second).hex()}

    # ------------------------------------------------------------ verification
    def verify(self, deed_id: Optional[str] = None, qr: Optional[str] = None,
               document: Optional[bytes] = None) -> dict:
        checks: List[dict] = []

        def check(name: str, ok: bool, detail: str) -> bool:
            checks.append({"check": name, "ok": bool(ok), "detail": detail})
            return ok

        qr_parts = None
        if qr:
            parts = qr.strip().split("|")
            if len(parts) != 6 or parts[0] != QR_PREFIX:
                check("qr_format", False, "QR code is not a Dolil Check code")
                return self._verdict(deed_id, checks)
            qr_parts = dict(zip(["prefix", "deed_id", "leaf_index", "key_id", "record_hash", "signature"], parts))
            deed_id = deed_id or qr_parts["deed_id"]
            ok, why = verify_with_listing(self.keys.infos, qr_parts["key_id"], deed_message(qr_parts["record_hash"]),
                                          qr_parts["signature"])
            check("qr_signature", ok, "QR signed by a registered office key" if ok else f"QR signature: {why}")

        row = self._record(deed_id, "deed") if deed_id else None
        if not check("found", row is not None, f"deed {deed_id} found in the registry" if row
                     else f"no deed {deed_id} in the registry"):
            return self._verdict(deed_id, checks)

        record = json.loads(row["record_json"])
        check("record_intact", canonical.record_hash(record) == row["record_hash"],
              "stored record matches its sealed hash" if canonical.record_hash(record) == row["record_hash"]
              else "stored record was changed after sealing")
        if qr_parts:
            same = (qr_parts["record_hash"] == row["record_hash"] and qr_parts["deed_id"] == deed_id
                    and qr_parts["leaf_index"] == str(row["leaf_index"]))
            check("qr_matches_record", same, "QR matches the registry record" if same
                  else "QR does not match the registry record (copied or forged QR)")
        ok, why = self.keys.verify(row["key_id"], deed_message(row["record_hash"]), row["signature"], row["signed_on"])
        check("office_signature", ok, "signed by the registering office" if ok else f"office signature: {why}")

        entry = canonical.canonical_bytes({"kind": "deed", "ref": deed_id, "record_hash": row["record_hash"],
                                           "key_id": row["key_id"], "sig": row["signature"],
                                           "signed_on": row["signed_on"]})
        sth = self.sth()
        idx = row["leaf_index"]
        in_log = (idx < sth["tree_size"] and merkle.leaf_hash(entry) == self.log.leaf(idx)
                  and merkle.verify_inclusion(merkle.leaf_hash(entry), idx, sth["tree_size"],
                                              self.log.inclusion(idx, sth["tree_size"]),
                                              bytes.fromhex(sth["root_hex"])))
        sth_ok = sth["signature"] is not None and self.keys.verify(
            sth["key_id"], sth_message(sth["tree_size"], sth["root_hex"], sth["timestamp"]), sth["signature"])[0]
        check("in_public_log", in_log and sth_ok,
              f"entry #{idx} proven in signed log of {sth['tree_size']} entries" if in_log and sth_ok
              else "entry is not provably in the public log")

        if document is not None:
            if record.get("doc_sha256") is None:
                check("document", False, "no document fingerprint was sealed with this deed")
            else:
                same = canonical.sha256_hex(document) == record["doc_sha256"]
                check("document", same, "document is byte-for-byte the registered one" if same
                      else "document has been altered since registration")

        buyers = [b["party_id"] for b in record["buyers"]]
        later = [dict(r) for r in self.conn.execute(
            "SELECT DISTINCT record_id, leaf_index FROM parties WHERE plot_id=? AND side='seller' AND leaf_index>?"
            " AND party_id IN (%s) ORDER BY leaf_index" % ",".join("?" * len(buyers)),
            (record["plot_id"], idx, *buyers))]
        mutation = self.conn.execute(
            "SELECT record_id, signed_on FROM records WHERE kind='mutation' AND deed_id=?", (deed_id,)).fetchone()
        context = {
            "deed": record,
            "later_transfers_by_buyers": [r["record_id"] for r in later],
            "current_holders": self.current_holders(record["plot_id"]),
            "mutation": {"mutation_id": mutation["record_id"], "date": mutation["signed_on"]} if mutation else None,
        }
        return self._verdict(deed_id, checks, context)

    @staticmethod
    def _verdict(deed_id: Optional[str], checks: List[dict], context: Optional[dict] = None) -> dict:
        failed = {c["check"] for c in checks if not c["ok"]}
        if failed - {"document"}:
            verdict = "INVALID"
            en, bn = "Not a genuine registered deed.", "এটি বৈধ নিবন্ধিত দলিল নয়।"
        elif "document" in failed:
            verdict = "ALTERED"
            en, bn = "The deed exists, but this copy has been altered.", "দলিলটি নিবন্ধিত, কিন্তু এই কপিটি পরিবর্তিত।"
        elif context and context["later_transfers_by_buyers"]:
            verdict = "GENUINE_SUPERSEDED"
            en = "Genuine deed, but the land was transferred again later."
            bn = "দলিলটি আসল, কিন্তু পরে জমিটি আবার হস্তান্তর হয়েছে।"
        else:
            verdict = "GENUINE_CURRENT"
            en, bn = "Genuine deed and the latest transfer.", "দলিলটি আসল এবং এটিই সর্বশেষ হস্তান্তর।"
        out = {"deed_id": deed_id, "verdict": verdict, "message_en": en, "message_bn": bn, "checks": checks}
        if context:
            out.update(context)
        return out

    def public_keys(self) -> list:
        return self.keys.public_listing()

    def close(self) -> None:
        self.conn.close()
