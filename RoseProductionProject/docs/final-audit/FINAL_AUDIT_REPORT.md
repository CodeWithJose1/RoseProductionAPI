# Final Audit Report — Rose Production Management and Forecasting System

| | |
|---|---|
| Date | 2026-11-22 (host run 10:42–10:44, GUI run 11:06–11:21, cloud regression 11:02–11:14, all −05:00) |
| System | `~/Documentos/DockerMySQL/RoseProductionAPI` on nobara-pc (Nobara 44, Python 3.14.8) |
| Database | MySQL 8.0.33 in Docker container `Mysqlcontainer`, database `RoseProductionDB` (50 rows) |
| API / GUI | Flask API 1.1.0 at `http://127.0.0.1:7003`; React GUI at `/app/` (bundle `index-CLqLDtTO.js`) |
| Requirements | the 9 functional and 6 non-functional requirements supplied as official for this audit |
| Safety | no `DROP`/`TRUNCATE`/`create_all`/`drop_all`, no schema change, no existing row modified or deleted, container and data folder untouched, no secret printed, nothing committed or pushed |

## 1. Executive summary

| Measure | Result | Calculation |
|---|---|---|
| Functional requirements | **9 PASS** · 0 PARTIAL · 0 FAIL · 0 NOT VERIFIABLE | 9 / 9 × 100 = **100 %** |
| Non-functional requirements | **5 PASS** · **1 PARTIAL** (NFR-02) · 0 FAIL · 0 NOT VERIFIABLE | 5 / 6 × 100 = **83.33 %** |
| All official requirements | 14 PASS of 15 | 14 / 15 × 100 = **93.33 %** |
| API CRUD | 35 of 35 required operations verified with SQL read-back | 7 entities × 5 operations → **100 %** |
| GUI | 46 of 46 required GUI items verified on the real system | 10 screens + 28 CRUD cells + 8 behaviours → **100 %** |
| Tests (final state) | 977 executions: 961 passed, **0 failed, 0 skipped**, 16 findings (8 distinct data/schema findings × 2 environments) | `TEST_EXECUTION_RESULTS.md` §6 |
| CRITICAL issues | none | |
| HIGH issues | 1 — schema accepts two harvests for one crop and day, corrupting forecast evaluation; **mitigated** in the API/GUI, **not closed** at the database level (needs approval of a schema change) | |

**Conclusion.** The database, the CRUD API and the GUI are implemented and work together on the real
system; all functional requirements and the three Project Advance criteria are met with reproducible
evidence. The project is **not** 100 % compliant with the 15 official requirements: NFR-02 is PARTIAL
because the database itself still accepts some inconsistent production records. The fix is a small,
documented schema change that was deliberately not applied without your approval.

## 2. Architecture (as implemented)

```
Browser ── /app/ (React 19 SPA, built with Vite 7) ──┐  same origin, HttpOnly session cookie
curl / scripts ── X-API-Key header ─────────────────┤
                                                     ▼
                     Flask 3.1.3 app factory (app.py) ─ auth.py · errors.py · validators.py
                     blueprints routes/{farms,lots,varieties,crops,seasons,harvests,
                                        forecasts,stats,gui}.py · forecasting.py
                                                     ▼ Flask-SQLAlchemy 3.1.1 / SQLAlchemy 2.1 / PyMySQL
                     MySQL 8.0.33 (Docker, port 3306) ─ RoseProductionDB: 7 tables, 7 FKs, 3 CHECKs,
                     1 UNIQUE, 4 triggers, 2 views, 6 procedures
```

## 3. Inventory (inspected, not assumed)

| Area | Found |
|---|---|
| Backend source | `app.py`, `config.py`, `auth.py`, `errors.py`, `validators.py`, `serializers.py`, `forecasting.py`, `models.py`, `routes/` (10 modules) — 2,491 lines |
| Original scripts | `test_connection.py`, `test_read.py` (kept, both run OK) |
| Models | 7 SQLAlchemy models mapping the existing tables; `db.create_all()` never called |
| Schema / migrations | no migration framework; `database/schema.sql` = schema-only dump; live schema read from `information_schema` |
| Routes | 7 resources × GET list, GET id, POST, PUT, DELETE; `/forecasts/status`, `/forecasts/summary`, `POST /forecasts/generate`; `/stats/production`, `/stats/dashboard`; `/auth/login|logout|status`; `/` public; `/app/*` GUI. No PATCH (405) |
| Authentication | `X-API-Key` (constant-time comparison) or GUI session cookie (HttpOnly, SameSite=Strict, signed) + CSRF header for session writes; login throttle (5 / 300 s); single shared key, no roles |
| Frontend | React 19, React Router 7, Recharts 3, Vite 7 — 29 source modules, 2,732 lines; 10 views; shipped `frontend/dist` |
| Forecasting | `forecasting.py`: moving average of the N (default 3) previous harvests of the same crop, ties by id, half-up rounding |
| Tests | pytest 233 (`tests/`), Vitest 60, Playwright 23 (`frontend/e2e`), audit harness `scripts/audit/` |
| Configuration | `.env` (git-ignored, not served, never printed) with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `API_KEY`; optional `SECRET_KEY`, `SESSION_HOURS`, `SESSION_COOKIE_SECURE`, `LOGIN_MAX_FAILURES`, `LOGIN_WINDOW_SECONDS`; `.env.example` |
| Docker | container `Mysqlcontainer`, image `mysql:8.0.33`, port 3306, bind mount `…/Mysql-data → /var/lib/mysql`, restart policy `no`; no Dockerfile/compose in the repository |
| Dependencies | `requirements.txt` (Flask 3.1.3, Flask-SQLAlchemy 3.1.1, SQLAlchemy 2.1.8, PyMySQL 1.2.4, python-dotenv 1.2.4, cryptography), `requirements-dev.txt` (pytest), `frontend/package.json` + lock |
| Documentation | `README.md`, `docs/INSTALLATION.md`, `DATABASE.md`, `API.md`, `GUI.md`, `TESTING.md`, `database/schema.sql`, this folder |

**Inconsistencies found in the inventory**

| # | Inconsistency | Action |
|---|---|---|
| I-1 | `docs/DATABASE.md` still described 49 rows / 7 forecasts; the database has 50 / 8 (forecast #40, created after the first delivery, treated as user data) | documented in DATABASE.md §10 |
| I-2 | `models.py` vs MySQL | none (`SCH-03`) |
| I-3 | Host `.venv`: SQLAlchemy 2.1.9 instead of pinned 2.1.8; `cryptography` absent; `pytest` absent | documented (INSTALLATION.md); the user installed pytest; works as is |
| I-4 | INSTALLATION.md spoke of a Docker *volume*; the data is a bind mount | corrected |
| I-5 | API.md lacked the error codes and rules introduced by the audit; TESTING/README counts outdated | updated |
| I-6 | No container definition and no project-level version control (the folder is untracked inside the home-directory git repository) | reported (LOW) |

## 4. Functional requirements (details: `FUNCTIONAL_REQUIREMENTS_TRACEABILITY.md`)

| ID | Priority | Key evidence | Status |
|---|---|---|---|
| FR-01 Rose varieties | High | CRUD 5/5 with SQL read-back, GUI create/edit/delete | PASS |
| FR-02 Cultivation lots | High | CRUD 5/5, farm relationship, GUI | PASS |
| FR-03 Daily harvests (date, lot, variety, quantity) | High | SQL join = API (`FR-03-01`), new consistency rules, GUI | PASS |
| FR-04 Commercial seasons | Medium | CRUD 5/5, date validation (API, CHECK, GUI), shrink conflict | PASS |
| FR-05 Historical consultation by date, variety, lot, season | High | each dimension = independent SQL (`FR-05-01…07`), GUI filters | PASS |
| FR-06 Total, average, minimum, maximum | High | known data and every variety = independent SQL, GUI cards | PASS |
| FR-07 Forecasts for future dates with a defined method | High | future date (2097), reproduces all 8 stored forecasts, GUI wizard | PASS |
| FR-08 Store, consult, compare with actual harvests | Medium | Pending → Evaluated with correct error, MAE/MAPE, GUI | PASS |
| FR-09 Referential integrity | High | 7 FKs RESTRICT, API 400/409, no orphans, GUI 409 | PASS |

## 5. Non-functional requirements (details: `NON_FUNCTIONAL_REQUIREMENTS_TRACEABILITY.md`)

| ID | Category | Key evidence | Status |
|---|---|---|---|
| NFR-01 | Performance | real DB: SQL medians 0.19–1.36 ms, API medians 3–32 ms, history/forecast queries on `idx_harvest_crop_date`; no threshold in the spec, none invented | PASS |
| NFR-02 | Security (integrity) | all FKs, CHECKs, UNIQUE, triggers enforced; but duplicate crop/day harvests and pre-planting dates accepted by the schema (`NFR-02-20`, `DQ-03`, `DQ-04`) | **PARTIAL** |
| NFR-03 | Performance (organization) | 3NF analysis on the live schema; data duplicates in 2 pairs of rows | PASS |
| NFR-04 | Availability | dump + restore into a new database, everything equal | PASS |
| NFR-05 | Scalability | schema fingerprint unchanged after adding/managing records; 100,020-harvest replica | PASS |
| NFR-06 | Security (access) | 105/105 unauthenticated CRUD attempts → 401, session/CSRF, key never in the browser | PASS |

## 6. Database verification

Seven InnoDB tables, all with integer surrogate keys; seven foreign keys (NOT NULL, RESTRICT); CHECKs
on harvest quantity, season dates and forecast estimate; one UNIQUE key (crop, forecast date); the
composite index `idx_harvest_crop_date`; four season triggers; two evaluation views; six procedures.
Verified on the running server (`SCH-01…03`, `NFR-02-01…21`, `DQ-01…09`). Backend connectivity:
`test_connection.py`, `ENV-03`, and every API write read back with SQL. Backup/restore: PASS.
Findings and proposed (unapplied) SQL: `docs/DATABASE.md §10`.

## 7. API, GUI and integration verification

- **API CRUD**: 35/35 operations, 26 negative cases, 7 GET-after-DELETE 404s, REAL-GET, 105
  unauthorized attempts — `API_CRUD_TEST_MATRIX.md`.
- **GUI**: 30-step workflow on the real system covering CRUD of all 7 entities, validation, API errors,
  forecasting (generate, save, evaluate), filters, statistics, API→GUI consistency, loading/empty/error
  states, browser-side secrets; 0 writes outside the test records — `GUI_INTEGRATION_TEST_REPORT.md`.
- **Integration (automated, replica)**: Playwright 23/23 with real browser input and SQL checks;
  production-data guard satisfied.

## 8. Issues discovered, severity and corrections

| ID | Severity | Issue | Status / correction | Files |
|---|---|---|---|---|
| H-1 | **HIGH** | Schema allows 2 harvests for one crop and day; `vw_forecast_status` duplicates the forecast and `vw_forecast_summary` is distorted (replica: MAE 50 → 750) | **Mitigated**: `POST/PUT /harvests` → 409 `DUPLICATE_RECORD`; GUI shows the message on the date field. **Open at DB level**: unique key proposed, needs approval | `routes/harvests.py`, `Harvests.jsx` |
| M-1 | MEDIUM | Harvest/forecast dates before the crop's planting date accepted (existing rows 16, 17, 18, forecast 7) | **Fixed for new/edited rows** (400 `DATE_BEFORE_PLANTING`, GUI date limits); existing rows reported, not modified | `routes/common.py`, `routes/harvests.py`, `routes/forecasts.py`, `Harvests.jsx`, `Forecasts.jsx` |
| M-2 | MEDIUM | Harvests could be dated in the future | **Fixed** (400 `FUTURE_HARVEST_DATE`, GUI max date = today) | `routes/harvests.py`, `Harvests.jsx` |
| M-3 | MEDIUM | A crop's planting date could be moved after its existing harvests/forecasts | **Fixed** (409 `PLANTING_DATE_CONFLICT`) | `routes/crops.py` |
| L-1 | LOW | No request-size limit | **Fixed** (1 MiB → 413) | `config.py` |
| L-2 | LOW | Colour contrast below WCAG AA on success badges (axe) | **Fixed** (`--success: #166534`; 0 violations) | `styles.css` |
| L-3 | LOW | Empty state said "No … yet" when filters hid existing rows | **Fixed** ("No matching records — change or clear the filters") | `CrudPage.jsx`, `Crops.jsx`, `Lots.jsx`, `Harvests.jsx`, `Forecasts.jsx` |
| L-4 | LOW | Failure to read the evaluation view was silent | **Fixed** (logged as a warning) | `routes/forecasts.py` |
| L-5 | LOW | `Lot.area` has no CHECK (API enforces > 0); varieties 6/7 and crops 7/8 duplicated | reported; CHECK proposed (approval) | – |
| L-6 | LOW | `GET /harvests` not paginated (3.0 s / 25 MB at 100,020 rows); date-only filter scans the table | reported (irrelevant at project size) | – |
| L-7 | LOW | Container definition not in the repo; restart policy `no`; no project VCS; host venv deviations | reported, documented in INSTALLATION.md | – |
| L-8 | LOW | Werkzeug development server; random `SECRET_KEY` per start unless set; in-memory throttle; single shared key | reported (local single-user deployment) | – |
| L-9 | LOW | Forecast evaluation needs a harvest on exactly the forecast date; only 1 real forecast evaluated | reported; no accuracy claim made | – |

After each code correction: pytest, Vitest, Playwright and the audit harness were re-run on the
replica, the corrected bundle was rebuilt reproducibly on nobara-pc, and the real system was
re-checked (host run 10:42 for the backend; browser checks and the 30-step GUI run for the final
bundle). The API version was raised to 1.1.0 so the host runner refuses to audit an older backend.

## 9. Security findings

No exploitable issue found: all protected operations require the key or a valid session (105/105
refusals, no database change); session cookie HttpOnly + SameSite=Strict without the key; CSRF header
enforced; no CORS; parameterized SQL (injection probes harmless, SQL text stored literally); JSON errors
without stack traces; 1 MiB body limit; the API key is absent from HTML/JS/CSS, browser storage and
cookies; `.env` is not served, not tracked by git and its values appear in no other file (2 scans);
`pip-audit` and `npm audit`: 0 known vulnerabilities. Limitations: L-8.

## 10. Regression results (details: `TEST_EXECUTION_RESULTS.md`)

| Suite | Real system | Replica / cloud |
|---|---|---|
| pytest | 233 / 233 (10:44) | 233 / 233 (11:03) |
| Vitest | 60 / 60 (nobara-pc VM, 16:05Z) | 60 / 60 (11:03) |
| Production build | reproducible, byte-identical | byte-identical |
| Playwright | not executable (see §11) | 23 / 23 (11:03) |
| Audit harness | 154 PASS, 8 FINDING, 0 FAIL (10:42) | 154 PASS, 8 FINDING, 0 FAIL (11:05) |
| GUI workflow | 30 / 30 (11:06–11:17) | – |
| Backup/restore | PASS (10:42) | – |
| axe-core | – | 0 violations, 11 views |

**Evidence categories.** *Previously existing:* first-delivery results (pytest 226/226 on the real DB at
09:18, Vitest 57, Playwright 23, workflows A–D) — used only as history. *New in this audit:* the
harness (162 checks), backup/restore check, secret scans, axe scan, scale test, duplicate-view
reproduction, 30-step GUI run, 7 pytest and 3 Vitest tests. *Corrected:* TC-07 reproduction test,
test year 2098 → 2001, E2E workflows B–D, one Vitest assertion (reasons in
`TEST_EXECUTION_RESULTS.md` §4). *Not executable:* Playwright on the real host; direct SQL during the
GUI run; host pytest after the last frontend-only fix.

## 11. Remaining limitations

1. NFR-02 PARTIAL until the unique key on `Harvest(crop_id, harvest_date)` is approved and applied.
2. Existing inconsistent rows (harvests 16, 17, 18; forecast 7; duplicates 6/7 and 7/8) await the data
   owner's decision.
3. The recovery database `RoseProductionDB_AuditRestore_20261122_104257` remains on the server for
   inspection; drop it manually when no longer needed.
4. Forecast accuracy is not established (one evaluated real forecast).
5. Playwright ran only against the replica.

## 11b. Addendum 2026-11-23 — duplicate prevention

The HIGH issue H-1 is now **closed at the database level**: the approved UNIQUE key
`unique_harvest_crop_date` was applied (with `unique_farm_name_location`, `unique_lot_farm_name` and
`unique_season_name_dates`), the API refuses duplicates of all seven entities (409, concurrency-safe)
and the GUI blocks repeated submissions. Real database after the change: pytest 256/256, harness
178 PASS / 7 FINDING / 0 FAIL, NFR-02-20 PASS. NFR-02 stays PARTIAL for the remaining items
(pre-planting dates accepted by the schema, no CHECK on `Lot.area`). Report:
[`DUPLICATE_DATA_PREVENTION_REPORT.md`](DUPLICATE_DATA_PREVENTION_REPORT.md).

## 12. Final conclusion

| Professor criterion | Verdict |
|---|---|
| Database Design and Implemented in MySQL / SQLite / Other | **MET** — MySQL 8.0.33, 7 related tables with keys, constraints, triggers, views and procedures, connected and verified |
| APIDB CRUD operations (100%) — Test Cases Passed | **MET — 100 %** (35/35), all test cases passed |
| GUI Design (100%) and integrated with APIDB | **MET — 100 %** (46/46), workflows demonstrated on the real system |

Requirements compliance: functional 100 %, non-functional 83.33 %, overall 93.33 %. The project can
be presented as meeting the three Project Advance criteria. It should be presented as fully compliant
with all 15 requirements only after the NFR-02 schema change is approved and applied, or with the
API-level mitigation explicitly disclosed.
