# Dolil Check | দলিল চেক

**A land deed verification prototype with digital signatures, tamper-evident records, and duplicate-sale prevention.**

Team Entropy · LandTech 2026 · Digital Land Records, Verification & Digitization  
Problem statement: P2 — Deed & Ownership Verification

Dolil Check is a bilingual prototype for sealing, logging and checking synthetic land-sale deeds. It can show whether a registered record and an optional uploaded deed file still match what an office signed, whether the record is proven in an append-only log, and whether the buyer later transferred the land. A share ledger refuses a second sale, an over-share sale or a sale by a non-owner.

This is **not a government service** and does not establish legal title. All people, offices, mouzas, plots and deeds in the demo are fictional.

## Problem and implemented solution

Paper copies can be altered, registration and mutation records can become disconnected, and a seller may try to transfer the same share twice. Dolil Check demonstrates a limited technical control:

1. Canonicalize deed fields (Unicode NFC, Bangla digit normalization and sorted JSON), hash them with SHA-256 and sign the record with an office Ed25519 key.
2. Append the signed record to an RFC 6962-style Merkle log and publish a signed tree head.
3. Print a QR containing the existing `DS1` payload and a verification link.
4. Verify the QR signature, stored record, Merkle inclusion proof and optional uploaded document fingerprint.
5. Track current shares in integer thousandths of a shotangsho and refuse duplicate, over-share and non-owner sales.
6. Link a signed mutation record to a known deed and flag deeds whose mutation remains pending beyond the configured example threshold.

### Integrity is not legal ownership

The system proves that a digital record or file matches what this prototype signed and logged. It does **not** prove that the first entry was legally or factually correct, resolve boundary disputes, replace official due diligence, or confer ownership. If incorrect facts are entered and approved initially, cryptography preserves those incorrect facts faithfully.

## Features present in the code

- Bangla/English interface with light and dark themes.
- Deed registration with seller/share checks and an optional PDF or image fingerprint.
- QR payload and QR image generation.
- `GENUINE_CURRENT`, `GENUINE_SUPERSEDED`, `ALTERED` and `INVALID` verification verdicts.
- Ed25519 office signatures with validity windows and key revocation checks.
- RFC 6962-style inclusion and consistency proofs.
- Current-holder share ledger and blocked-attempt audit list.
- Mutation entry, overdue-mutation flags and refused-mutation list.
- Printable browser certificate for newly issued records.
- Synthetic deterministic seed data with planted fraud attempts.
- CLI verification client and automated unit/API tests.

No government portal, production registry, identity provider, payment service or real e-mutation system is integrated.

## Architecture and technology

| Layer | Implementation |
| --- | --- |
| Web UI | Plain HTML, CSS and JavaScript; no frontend build step |
| HTTP API | Starlette ASGI application served by Uvicorn |
| Registry | SQLite database managed directly by `backend/app/registry.py` |
| Cryptography | `cryptography`: Ed25519 signatures and SHA-256 hashing |
| Transparency log | In-project RFC 6962-style Merkle tree implementation |
| QR | `qrcode` with Pillow |
| Tests | Python `unittest` and HTTPX |

Important files:

```text
backend/app/canonical.py   canonical JSON and hashing
backend/app/signing.py     office keys, validity windows and signature domains
backend/app/merkle.py      inclusion and consistency proofs
backend/app/registry.py    SQLite ledger, business rules and verification
backend/app/main.py        Starlette routes and API
backend/app/seed.py        deterministic synthetic dataset and demo files
backend/app/cli.py         command-line demo client
backend/web/               bilingual web pages and shared static assets
backend/tests/             unit and API tests
```

## Install and configure

Requires Python 3.10 or newer.

```bash
git clone <NEW_REPOSITORY_URL>
cd dolil-check/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Configuration is optional. Copy the example only when overriding a default:

```bash
cp ../.env.example ../.env
```

The application does not automatically load `.env`; export any values you use in your shell or deployment platform. Existing `DOLIL_*` names are retained for compatibility with deployments and verification links.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DOLIL_DATA` | `<repo>/data/runtime` | Runtime SQLite database, private office keys and demo output |
| `DOLIL_PUBLIC_URL` | Current request base URL | Public base URL encoded into newly generated QR links |
| `DOLIL_NO_APP` | unset | Set to `1` only for tests/imports that create their own app |

## Database initialization and synthetic seed

There is no separate migration tool or migration command. `Registry` creates the SQLite schema when it opens a new database. Generate the deterministic synthetic demo database from `backend/`:

```bash
python -m app.seed
```

If runtime data already exists, the command refuses to overwrite it. To deliberately replace local runtime data:

```bash
python -m app.seed --reset
```

`--reset` deletes and recreates `DOLIL_DATA`; do not run it against data you need to preserve. Restart the server after reseeding so it reloads the new database and keys.

## Run

From `backend/`, with the virtual environment active:

```bash
uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000>. To create QR links reachable from a phone on the same Wi-Fi:

```bash
DOLIL_PUBLIC_URL=http://192.168.0.105:8000 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Replace the example address with the laptop's LAN address. Newly generated QR links use this value; existing signed QR payloads are not rewritten.

Docker is also supported:

```bash
docker compose up --build
```

The container initializes synthetic data only when its persistent volume has no database.

## Web pages

| Page | URL | Purpose |
| --- | --- | --- |
| Dashboard | `/` | Counts, blocked attempts, pending mutations and signed log head |
| Register | `/register` | Register and seal a synthetic sale deed |
| Mutation | `/mutation` | Record a mutation tied to a registered deed |
| Verify | `/v` | Check a deed number/QR and optionally compare a document file |
| Guide | `/guide` | Bilingual end-user instructions |
| Certificate | `/deed?id=...` | Print the newly rendered QR certificate |
| API index | `/api` | JSON endpoint list |

## Demo data and CLI

The deterministic seed contains a fictional story in which Rahim sells 10 shotangsho of fictional Nodipara dag 123 to Karim, later attempts a second sale to Jabbar, and an altered PDF changes 10 to 16. Names and plots are invented solely for the prototype.

From `backend/`, with the server running:

```bash
python -m app.cli verify \
  --qr-file ../data/runtime/demo/qr.txt \
  --document ../data/runtime/demo/deed_genuine.pdf

python -m app.cli verify \
  --qr-file ../data/runtime/demo/qr.txt \
  --document ../data/runtime/demo/deed_altered.pdf

python -m app.cli flags --as-of 2026-10-10
```

## Test

From `backend/`:

```bash
python -m unittest discover -s tests -t .
```

There is no frontend compilation or production-build command because the UI is served as plain static HTML, CSS and JavaScript.

## API summary

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/baselines` | Add office-verified synthetic starting holders |
| `POST` | `/deeds` | Register a deed subject to share-ledger rules |
| `GET` | `/deeds/{id}` | Return a sealed record and inclusion proof |
| `GET` | `/deeds/{id}/qr`, `/qr.png` | Return QR payload or image |
| `POST` | `/verify` | Verify a QR/deed and optional base64 document |
| `POST` | `/mutations` | Record a mutation tied to a deed |
| `GET` | `/flags` | Return overdue and refused mutation flags |
| `GET` | `/plots`, `/plots/all` | Return current holders and plot history |
| `GET` | `/log/sth`, `/entries`, `/inclusion`, `/consistency` | Return log state and proofs |
| `GET` | `/keys` | Return public office keys and validity metadata |
| `GET` | `/rejections` | Return refused registration/mutation attempts |

## Synthetic-data disclosure

All data generated by `backend/app/seed.py` is synthetic and deterministic. No real names, NID numbers, phone numbers, addresses, land records or government systems are used or queried. Runtime data, private keys and generated demo files are kept under `data/runtime/` and are intentionally excluded from Git.

## Known limitations

- Prototype office private keys are local PEM files; a production design would require controlled key custody such as an HSM.
- Only new sale registrations are modeled. Legacy holdings enter through an office-approved synthetic baseline.
- Inheritance and other transfer types are outside the current scope.
- The 60-day mutation threshold is an example configuration, not a statement of law or policy.
- Document comparison is byte-for-byte hashing, not OCR or semantic fraud detection.
- The prototype does not authenticate users or implement production authorization/auditing controls.
- The signed log only provides tamper evidence if signed tree heads are independently published or monitored.
- Browser-rendered certificates are presentation documents; the signed payload and proofs are the integrity evidence.

## Compatibility note

The product was renamed from Dolil Seal to **Dolil Check**. Internal values that participate in verification remain unchanged:

- signature domain strings `dolil-seal/v1/...`;
- QR format prefix `DS1`;
- environment variables `DOLIL_DATA`, `DOLIL_PUBLIC_URL` and `DOLIL_NO_APP`;
- SQLite filename `dolil.db` and existing API paths.

Changing these would break existing signatures, QR payloads, data locations or deployments. New UI and newly rendered certificates show the Dolil Check brand; previously issued files and signed records are not rewritten.

## Open-source dependencies

| Library | Licence | Use |
| --- | --- | --- |
| Starlette | BSD-3-Clause | ASGI API and routes |
| Uvicorn | BSD-3-Clause | Development/production ASGI server |
| cryptography | Apache-2.0 / BSD | Ed25519 and hashing support |
| qrcode | BSD | QR images |
| Pillow | HPND | QR PNG support through `qrcode[pil]` |
| HTTPX | BSD-3-Clause | API tests |
| Hind Siliguri, Tiro Bangla, Noto Sans Bengali | SIL Open Font License | Web typography |

## AI tool disclosure

Claude (Anthropic) and Codex (OpenAI) were used to help draft and revise application code, tests, UI copy, documentation and design. The team is responsible for reviewing, understanding, testing and presenting every change. This disclosure should be updated if additional AI tools are used.

## Team

Team Entropy, Daffodil International University. Student and mentor details should be completed by the team before submission.

## Licence

MIT. See [LICENSE](LICENSE).
