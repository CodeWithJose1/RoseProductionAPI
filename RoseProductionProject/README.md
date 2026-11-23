# Rose Production Management and Forecasting System

Database-driven application for a floricultural farm: it manages farms, cultivation
lots, rose varieties, crops, commercial seasons (Valentine's Day, Mother's Day…),
daily harvests and production forecasts, and analyses historical production.

```
React GUI (/app/)  ──HTTP/JSON──▶   Flask REST API (:7003)  ──PyMySQL──▶  MySQL 8.0 (Docker: Mysqlcontainer)
   browser                           auth · validation · stats ·            RoseProductionDB
                                     moving-average forecasting             7 tables · 2 views · 4 triggers · 6 procedures
```

| Layer | Technology |
|---|---|
| Database | MySQL 8.0.33 in Docker (`Mysqlcontainer`), database `RoseProductionDB` |
| API | Python 3, Flask 3.1, Flask-SQLAlchemy 3.1, SQLAlchemy 2.1, PyMySQL |
| GUI | React 19 + Vite 7 (JavaScript), React Router, Recharts, lucide icons |
| Tests | pytest (DB + API), Vitest + React Testing Library (GUI), Playwright (end-to-end) |

## Features

- **CRUD for the 7 entities** (Farm, Lot, RoseVariety, Crop, Season, Harvest, Forecast) through the API
  and the GUI, with validation, clear error messages and protection against deleting referenced records.
- **Dashboard** with live figures: totals, production by variety, by season, harvests over time,
  forecast vs actual, upcoming seasons and pending forecasts.
- **Historical consultation** (FR-05) by date range, variety, lot, crop and season.
- **Production statistics** (FR-06): total, average, minimum and maximum, grouped by variety, lot,
  season, crop, month or date.
- **Forecasting** (FR-07/08): moving average of the 3 previous harvests of a crop (the method already
  used by the stored forecasts), preview → save, and evaluation with the `vw_forecast_status` /
  `vw_forecast_summary` views (MAE, MAPE).
- **Security** (NFR-06): API key (`X-API-Key`) for scripts; the GUI signs in once and receives an
  HttpOnly, SameSite=Strict session cookie — the API key is never stored in the browser or in the
  front-end code. CSRF header check, login throttling, security headers.
- **Responsive GUI**: sidebar navigation that collapses to a menu on phones, tables that become cards.

## Quick start

Full instructions: [docs/INSTALLATION.md](docs/INSTALLATION.md).

```bash
cd ~/Documentos/DockerMySQL/RoseProductionAPI
docker start Mysqlcontainer                    # 1. database
source .venv/bin/activate
pip install -r requirements.txt                # first time only
python app.py                                  # 2. API + GUI on http://127.0.0.1:7003
```

Open **http://127.0.0.1:7003/app/** and sign in with the `API_KEY` value from `.env`.
The GUI is already built (`frontend/dist`), so Node.js is only needed to modify the GUI
or to run the front-end tests.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest                               # database + API + security (256 tests)
cd frontend && npm install
npm test                                       # GUI component tests (72 tests)
npx playwright test                            # end-to-end workflows A–D + duplicates (26 tests, API must be running)
```

All suites use isolated `TEST_`/`E2E_` records and verify at the end that every pre-existing row is
unchanged. See [docs/TESTING.md](docs/TESTING.md) for the test cases and the latest results.

## Documentation

| Document | Content |
|---|---|
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Dependencies, Docker, backend, frontend, environment variables, start/stop |
| [docs/DATABASE.md](docs/DATABASE.md) | Tables, relationships, constraints, views, triggers, procedures, indexes, SQL examples |
| [docs/API.md](docs/API.md) | Every endpoint with request/response examples, authentication, error codes |
| [docs/GUI.md](docs/GUI.md) | Screens, navigation, forms, dashboard and GUI ↔ API integration |
| [docs/TESTING.md](docs/TESTING.md) | Test cases, procedures, expected vs actual results, limitations |
| [database/schema.sql](database/schema.sql) | Schema-only dump (no data) of `RoseProductionDB` |
| [docs/final-audit/DUPLICATE_DATA_PREVENTION_REPORT.md](docs/final-audit/DUPLICATE_DATA_PREVENTION_REPORT.md) | Duplicate prevention (2026-11-23): uniqueness rules, root cause, constraints, API/GUI changes, tests |
| [docs/final-audit/FINAL_AUDIT_REPORT.md](docs/final-audit/FINAL_AUDIT_REPORT.md) | Final audit (2026-11-22): requirement traceability FR-01…FR-09 / NFR-01…NFR-06, CRUD matrix, GUI integration, test execution, professor checklist |

## Project structure

```
RoseProductionAPI/
├── app.py               Flask application factory and entry point (port 7003)
├── config.py            configuration from .env
├── models.py            SQLAlchemy models (mapped to the existing tables)
├── auth.py              X-API-Key + GUI session authentication
├── errors.py            JSON error format and MySQL error translation
├── validators.py        request validation
├── serializers.py       model → JSON
├── forecasting.py       moving-average forecast
├── routes/              one blueprint per resource + /stats + GUI serving
├── tests/               pytest suites (database, API, security)
├── frontend/            React + Vite GUI (src/, e2e/, dist/)
├── database/schema.sql  schema-only dump
├── scripts/backup_db.sh database backup helper
├── scripts/audit/       final-audit harness (HTTP+SQL audit, backup/restore check, duplicate inspection, host runners)
├── scripts/db/          approved schema migrations (add_unique_constraints.sh)
├── database/migrations/ SQL of the approved migrations
├── docs/                documentation and screenshots
├── test_connection.py   original connection check
└── test_read.py         original read check
```

## Security notes

- `.env` holds the database credentials and the API key; it is git-ignored and must never be shared.
  `.env.example` lists the variables with placeholders.
- `backups/` (database dumps with production data) is git-ignored.

## Authors

David Diaz, Jose Cabascango — Database course project.
