# Dolil Check: project notes for Codex

LandTech 2026 hackathon (Daffodil International University), Team Entropy.
Track: Digital Land Records, Verification & Digitization. Problem statement: **P2 Deed & Ownership Verification**.
Round 1 deadline: **16 October 2026** (concept note PDF ≤4 pages, repo link, demo video ≤3 min, aim for 2:00).

## What it does
Seals land deeds (Ed25519 office signature over canonical JSON), appends them to a public RFC 6962 Merkle log,
prints a QR (`DS1|deed_id|leaf|key_id|record_hash|sig`, encoded as a `/v?q=` link), blocks double sales via a
share ledger, links AC Land mutations to deeds, and verifies deeds (GENUINE_CURRENT / GENUINE_SUPERSEDED / ALTERED / INVALID).

## Layout
- `backend/app/canonical.py` NFC + Bangla digits + sorted JSON hashing
- `backend/app/signing.py` office keys, validity windows, revocation
- `backend/app/merkle.py` inclusion and consistency proofs
- `backend/app/registry.py` SQLite ledger, deeds, mutations, verification (all business rules live here)
- `backend/app/main.py` Starlette API + page routes
- `backend/web/` Bangla pages: plain HTML/CSS/JS, no build step (`static/app.js` has shared helpers)
- `backend/app/seed.py` synthetic data with planted fraud; `backend/app/cli.py` demo client

## Commands (run from backend/, venv: `source .venv/bin/activate`)
- Tests: `python -m unittest discover -s tests -t .`
- Seed: `python -m app.seed --reset`
- Run: `uvicorn app.main:app --reload` → http://127.0.0.1:8000

## Rules that must not be broken (rulebook section 8: instant disqualification)
- Synthetic data only. Never add real names, NID numbers, phone numbers, addresses or real land records.
- Never scrape or query any government portal.
- Pages must stay clearly marked as a prototype with fictional data; never imitate a government website.
- Areas are integer thousandths of a shotangsho; never floats in signed records.
- Both students must be able to explain every change, so keep code simple and comment the why.
- Keep the README's AI-disclosure section accurate.
