# Installation and operation

Target machine: Linux (Nobara/Fedora). Project folder: `~/Documentos/DockerMySQL/RoseProductionAPI`.

## 1. Dependencies

| Component | Version used | Needed for |
|---|---|---|
| Docker | any recent | MySQL container `Mysqlcontainer` |
| MySQL | 8.0.33 (in the container) | database `RoseProductionDB` |
| Python | 3.10+ (project `.venv` uses 3.14) | API and backend tests |
| Python packages | `requirements.txt` (Flask 3.1.3, Flask-SQLAlchemy 3.1.1, SQLAlchemy 2.1.8, PyMySQL 1.2.4, python-dotenv 1.2.4, cryptography) | API |
| pytest | `requirements-dev.txt` | backend tests |

Note (final audit): the project `.venv` on nobara-pc had SQLAlchemy 2.1.9 instead of the pinned 2.1.8,
no `cryptography` and, initially, no `pytest`. The API and all 233 backend tests work with it;
`pip install -r requirements.txt -r requirements-dev.txt` aligns it with the pinned versions.
| Node.js | 22.12+ (or 24) and npm | **only** to rebuild the GUI or run the front-end/E2E tests |

The GUI is shipped already built in `frontend/dist`, so running the application needs only Docker
and Python.

## 2. Database (Docker)

The container and its data folder already exist; nothing has to be created or imported.

Container facts read with `docker inspect` during the final audit (2026-11-22):

| Property | Value |
|---|---|
| Image | `mysql:8.0.33` |
| Port | host `3306` → container `3306/tcp` |
| Data | bind mount `/home/jose/Documentos/DockerMySQL/Mysql-data` → `/var/lib/mysql` |
| Restart policy | `no` — after a reboot the container must be started by hand (`docker start Mysqlcontainer`) |

The command or compose file that originally created the container is not part of this repository.
Do **not** remove or recreate the container: the data lives in the bind-mounted folder above. If you
want it to start automatically, `docker update --restart unless-stopped Mysqlcontainer` changes only
the restart policy (optional; not applied by the audit).

```bash
docker ps -a --filter name=Mysqlcontainer     # status
docker start Mysqlcontainer                   # start
docker logs --tail 20 Mysqlcontainer          # wait for "ready for connections"
```

Check the schema without exposing the password (it is read from `.env`):

```bash
cd ~/Documentos/DockerMySQL/RoseProductionAPI
set -a; source .env; set +a
docker exec -e MYSQL_PWD="$DB_PASSWORD" Mysqlcontainer mysql -u "$DB_USER" "$DB_NAME" -e "SHOW FULL TABLES;"
```

Backup before any maintenance: `./scripts/backup_db.sh` (see [DATABASE.md](DATABASE.md#9-backup-and-recovery-nfr-04)).

## 3. Environment variables (`.env`)

`.env` lives in the project root, is git-ignored and is never sent to the browser.
`.env.example` shows the format:

| Variable | Required | Description |
|---|---|---|
| `DB_HOST`, `DB_PORT` | yes | MySQL address published by Docker (e.g. `127.0.0.1`, `3306`) |
| `DB_NAME` | yes | `RoseProductionDB` |
| `DB_USER`, `DB_PASSWORD` | yes | MySQL account |
| `API_KEY` | yes | key for the `X-API-Key` header and for signing in to the GUI |
| `SECRET_KEY` | no | signs the GUI session cookie; if absent a random key is generated at start-up (users sign in again after a restart) |
| `SESSION_HOURS` | no | GUI session lifetime, default 8 |
| `SESSION_COOKIE_SECURE` | no | `true` only when served over HTTPS |
| `LOGIN_MAX_FAILURES`, `LOGIN_WINDOW_SECONDS` | no | sign-in throttling, default 5 failures / 300 s |

The existing `.env` already contains the required variables; the optional ones can be added later.

## 4. Backend (Flask API + GUI)

```bash
cd ~/Documentos/DockerMySQL/RoseProductionAPI
source .venv/bin/activate
pip install -r requirements.txt          # first time (adds 'cryptography' to the existing packages)
python test_connection.py                # optional: "Connection successful!"
python app.py                            # serves http://127.0.0.1:7003
```

- API: `http://127.0.0.1:7003/` (public health message), protected endpoints need the key.
- GUI: **http://127.0.0.1:7003/app/** → sign in with the value of `API_KEY`.

The server listens on 127.0.0.1 only (not reachable from other machines) and runs with
`debug=False`. Do not start two instances on port 7003.

## 5. Frontend (only to develop or test the GUI)

Install Node.js once (Fedora/Nobara): `sudo dnf install nodejs npm` (check `node --version` ≥ 22.12).

```bash
cd ~/Documentos/DockerMySQL/RoseProductionAPI/frontend
npm install
npm run dev          # development server http://127.0.0.1:5173/app/ (proxies the API on :7003)
npm run build        # rebuilds frontend/dist used by Flask
```

## 6. Running the tests

```bash
cd ~/Documentos/DockerMySQL/RoseProductionAPI
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest                     # database + API + security; uses the database in .env

cd frontend
npm test                             # GUI component tests (no database needed)
npx playwright install chromium      # once
npx playwright test                  # end-to-end; requires `python app.py` running
```

Final-audit scripts (run on the machine that hosts Docker, with `python app.py` running):

```bash
bash scripts/audit/run_host_audit.sh        # environment, schema, pytest, HTTP+SQL audit, backup/restore check, secret scan
bash scripts/audit/backup_restore_check.sh  # dump RoseProductionDB and restore it into a NEW database for comparison
```

Duplicate-prevention fix (2026-11-23, already applied on nobara-pc):

```bash
bash scripts/apply_duplicate_fix.sh   # backup + approved UNIQUE constraints + API 1.2.0 on port 7004 + verification
kill $(cat docs/final-audit/evidence/duplicates/host/api_7004.pid)   # stop the verification API afterwards
```

Running it again is safe: existing constraints are skipped and a new backup is taken first.

The backup/restore check never writes to `RoseProductionDB`; it leaves the recovery database
`RoseProductionDB_AuditRestore_<timestamp>` for inspection and prints the command to drop it.
Evidence is written to `docs/final-audit/evidence/`.

All database-touching tests create their own `TEST_…`/`E2E_…` rows, delete them by id, and finish with a
guard that compares every pre-existing row with a snapshot taken at the start. Run `./scripts/backup_db.sh`
first anyway. Details: [TESTING.md](TESTING.md).

## 7. Stopping

```bash
# API: press Ctrl+C in the terminal running python app.py
deactivate                     # leave the virtual environment
docker stop Mysqlcontainer     # optional: stop MySQL (data stays in the bind-mounted Mysql-data folder)
```

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `/app/` returns `GUI_NOT_BUILT` | run `npm install && npm run build` in `frontend/` |
| GUI shows "Cannot reach the API" | start `python app.py`; check port 7003 |
| GUI shows "Invalid access key" | use the exact `API_KEY` value from `.env` (no spaces) |
| API returns 503 "database is not available" | `docker start Mysqlcontainer`, check `DB_HOST/DB_PORT` |
| `RuntimeError: 'cryptography' package is required` | `pip install -r requirements.txt` |
| 401 after restarting the API | expected without `SECRET_KEY`: sign in again |
| Playwright cannot launch Chromium on Fedora | `npx playwright install chromium`; or run with an installed Chrome: `npx playwright test --project=desktop` after setting `channel: 'chrome'` in `playwright.config.js` |
