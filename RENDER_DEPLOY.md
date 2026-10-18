# Free Render competition demo

This deploy is a disposable demonstration with synthetic data. It uses one free Python web service, no database service, no persistent disk and no paid resource. Render's free web-service filesystem is ephemeral: the SQLite database, generated signing keys and demo files can disappear whenever the service spins down, restarts or redeploys. A fresh instance creates a new internally consistent synthetic dataset.

Records or QR codes downloaded from an earlier ephemeral instance might not verify after reinitialization because that instance's generated keys and database no longer exist.

## Import from GitHub

The repository includes `render.yaml`, so the shortest path is:

1. Sign in to the Render Dashboard and connect the GitHub account that can read `kmsajid044-ship-it/dolil-check`.
2. Choose **New → Blueprint**.
3. Select `https://github.com/kmsajid044-ship-it/dolil-check` and branch `main`.
4. Render reads the root-level `render.yaml`. Confirm the service values below.
5. Enter `DOLIL_ADMIN_PASSWORD` privately when Render prompts. Use a strong credential shared only with the presenting team.
6. Create/apply the Blueprint. Do not add a disk, database, cron job or paid instance.

## Exact service values

These are the equivalent values for **New → Web Service** if configuring manually:

| Dashboard field | Value |
| --- | --- |
| Service name | `dolil-check` |
| Repository | `https://github.com/kmsajid044-ship-it/dolil-check` |
| Branch | `main` |
| Runtime | `Python 3` |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` |
| Instance Type | `Free` |
| Health Check Path | `/health` |

Do not set a persistent disk. Do not create a separate static site: Starlette serves the frontend and API from the same service.

## Environment variables

| Name | How to configure | Secret? |
| --- | --- | --- |
| `DOLIL_DATA` | Set to `/tmp/dolil-check-runtime` | No |
| `DOLIL_ADMIN_PASSWORD` | Enter a strong team-only value in the Render Dashboard | **Yes** |
| `DOLIL_SESSION_SECRET` | Let the Blueprint generate it, or use Render's **Generate** option | **Yes** |

Do not create `DOLIL_PUBLIC_URL` on Render. The application uses Render's provided `RENDER_EXTERNAL_URL` for newly generated HTTPS verification links. `PORT` and `RENDER_EXTERNAL_URL` are provided by Render.

Never put either secret in Git, frontend JavaScript, a URL, browser local storage or screenshots. The administrator password is sent only in the HTTPS login request; successful login uses a signed, HttpOnly, SameSite session cookie plus a per-session CSRF token.

## Post-deploy smoke tests

Replace `<render-origin>` with the HTTPS URL shown by the Render Dashboard.

1. Open `<render-origin>/health`. Expect JSON containing `"ok": true`, `"mode": "competition-demo"` and a nonzero `log_size`.
2. Open `<render-origin>/`. Confirm the bilingual competition-demo banner and synthetic dashboard data.
3. Open `<render-origin>/v` and verify a seeded deed from the dashboard. Public verification must work without login.
4. In a private/incognito browser, try to submit registration or mutation. Expect **401 / demo administrator login required**.
5. Open `<render-origin>/admin/login`, sign in with the private `DOLIL_ADMIN_PASSWORD`, then perform one demonstration write.
6. Open the new deed's QR endpoint or certificate and confirm its verification URL begins with the actual `https://...onrender.com` origin, never localhost.
7. Confirm a guessed private-key path such as `<render-origin>/data/runtime/keys/private/example.pem` returns 404.

There is deliberately no public reset endpoint.

## Cold starts and ephemeral storage

- A free Render web service can spin down after 15 minutes without inbound traffic. The next request can take about a minute while it starts.
- The local filesystem is ephemeral. Writes can disappear on spin-down, restart or redeploy.
- Startup seeds only an empty runtime. A complete runtime is validated and reused. Partial or corrupt runtime data causes startup to fail clearly; the application never silently deletes it.
- Do not use automated keep-alive traffic. Do not promise that demo writes or downloaded records will survive a restart.

## Local backup demo

Keep a local backup ready for the presentation. From `backend/`:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt

# Use the existing local synthetic runtime, or choose a separate empty directory.
export DOLIL_DATA="$(pwd)/../data/runtime"
export DOLIL_ADMIN_PASSWORD='choose-a-local-demo-password'
export DOLIL_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

uvicorn app.main:app --host 127.0.0.1 --port 3000 --workers 1
```

Open `http://127.0.0.1:3000`. Do not run `python -m app.seed --reset` against data you need to preserve.

## Official Render references

- [Blueprint YAML reference](https://render.com/docs/blueprint-spec)
- [Web-service port binding](https://render.com/docs/web-services#port-binding)
- [Default environment variables](https://render.com/docs/environment-variables)
- [Free web-service limits](https://render.com/docs/free)
