# GUI Integration Test Report

## 1. What the GUI is (from the source, not from the documentation)

| Aspect | Actual implementation |
|---|---|
| Framework | React 19 single-page application built with Vite 7 (`frontend/`), React Router 7, Recharts 3, lucide-react icons |
| Delivery | Production build in `frontend/dist`, served by Flask at `/app/` (`routes/gui.py`); browser routes such as `/app/harvests` fall back to the SPA |
| API access | `src/api/client.js` → `fetch` to the same origin with the session cookie; no API key in the code, the bundle or browser storage; writes add `X-Requested-With: RoseProductionGUI` |
| Authentication | Login page posts the key once to `POST /auth/login`; the server answers with an HttpOnly, SameSite=Strict cookie |
| Data | Every table, card and chart is filled from API responses (no fixtures in the production code; `src/test/` fixtures are used only by Vitest) |
| Pages (10 views) | Login · Dashboard · Production analysis · Farms · Lots · Rose varieties · Crops · Seasons · Harvests · Forecasts (with the *Generate forecast* dialog); unknown paths redirect to the Dashboard |
| Shared components | `CrudPage`, `DataTable` (search, sort, 10 rows per page, empty state), `ResourceFormModal`, `ConfirmDialog`, `FormField`, `States` (loading/empty/error), `Charts`, `Layout` |

Bundle audited: `/app/assets/index-CLqLDtTO.js` (+ `index-CL6YbocT.css`), rebuilt byte-for-byte
identically on nobara-pc and in the cloud workspace.

## 2. Workflow on the real system

**Environment.** nobara-pc: Docker container `Mysqlcontainer` (MySQL 8.0.33) running, `python app.py`
serving `http://127.0.0.1:7003`, GUI at `/app/`, signed in by the user (the audit never typed the key).

**How it was driven.** In the Claude desktop app's browser pane, through the GUI's own forms, selects,
buttons, filters and confirm dialogs (DOM events dispatched to the React controls). All requests issued
by the GUI were logged by wrapping `window.fetch`; persistence was checked with **independent** reads
(`GET` by id or list in a separate request — each API request opens a new database session and reads
MySQL; there is no cache). Time: 2026-11-22 11:06–11:17 −05:00. Raw evidence:
`evidence/gui_real_system_run.json` (30 steps, request log, before/after counts).

Steps 1–4 of the requested workflow (start database, backend, frontend, open the GUI) were verified by
the host run at 10:42 (`logs/01_docker_status.log`: container Up; `logs/05_original_test_connection.log`:
MySQL 8.0.33 `RoseProductionDB`; `logs/07_api_version.log`: API 1.1.0) and by loading `/app/`. The
frontend has no separate server in production: Flask serves the built SPA.

| Step | What was done in the GUI | Request(s) issued by the GUI | Independent verification | Result |
|---|---|---|---|---|
| Baseline | page counts and dashboard | `GET` lists, `/stats/dashboard` | 1/3/7/8/3/20/8 rows, 26,480 stems | – |
| GUI-01 | Farms → New farm `GUIAUDIT_160718_Farm` | `POST /farms` 201 | `GET` → farm 202 with the sent values; row + toast shown | PASS |
| GUI-02 | Edit farm location | `PUT /farms/202` 200 | location updated | PASS |
| GUI-03/04 | Lots → New lot (farm 202, 1.5 ha), edit to 2.25 | `POST /lots` 201, `PUT /lots/190` 200 | area 2.25; farm 202 lists lot 190 | PASS |
| GUI-05/06 | Rose varieties → New (Lavender), edit to White | `POST /varieties` 201, `PUT /varieties/204` 200 | colour White | PASS |
| GUI-07 | Seasons → end date before start | none (client rule) | message "End date must be on or after the start date", dialog stays open | PASS |
| GUI-08/09 | Past season 2001-02-01…20, edited to …28; future season 2097-02 | `POST /seasons` 201 ×2, `PUT /seasons/163` 200 | end 2001-02-28 (28 days) | PASS |
| GUI-10 | Crops → New crop (lot 190, variety 204, 2001-01-15), edit to 2001-01-10 | `POST /crops` 201, `PUT /crops/167` 200 | planting 2001-01-10 | PASS |
| GUI-11 | Harvests → quantity 0 | none (client rule) | "Quantity must be greater than zero" | PASS |
| GUI-12 | Three harvests 1000 / 1200 / 1400 | `POST /harvests` 201 ×3 | ids 229–231 with those values | PASS |
| GUI-13 | Second harvest for the same crop and day | `POST /harvests` **409** | API message shown on the form: "Crop #167 already has a harvest record on 2001-02-04 (harvest #231); edit that record instead" | PASS |
| GUI-14 | Edit harvest 1400 → 1500 | `PUT /harvests/231` 200 | quantity 1500; row shows Date, Variety, Lot, Crop, Season, Stems | PASS |
| GUI-15 | Generate forecast with only 1 earlier harvest | `POST /forecasts/generate` **400** | "Not enough history: … needs 3 … but only 1 exist." | PASS |
| GUI-16 | Generate + save forecast for **2097-02-10** (future) | `generate` 200 (preview) + 201 (save) | estimate 1,233.33, formula `(1500 + 1200 + 1000) / 3`, harvests used listed; forecast 63 Pending | PASS |
| GUI-17 | Generate + save forecast for 2001-02-10 | `generate` 200 + 201 | forecast 64 Pending | PASS |
| GUI-18 | Register the actual harvest 2001-02-10 = 1300 | `POST /harvests` 201 | Forecasts table: 64 → Actual 1,300, Abs. error 66.67 (5.13 %), **Evaluated**; 63 still Pending; summary MAE 58.34, MAPE 4.13 (screenshot `real_06_gui_forecast_evaluated.jpg`) | PASS |
| GUI-19 | Harvest filters one at a time: variety, lot, season, date range, single date | `GET /harvests?variety_id=…`, `?lot_id=…`, `?season_id=…`, `?date_from&date_to` | 4 / 4 / 4 / 2 / 1 records, the expected rows | PASS |
| GUI-20 | Production analysis filtered by the test variety | `GET /stats/production?group_by=variety&variety_id=204` | cards 5,000 / 4 / 1,250 / 1,000 / 1,500 = known data 1000, 1200, 1500, 1300 | PASS |
| GUI-21 | Dashboard | `GET /stats/dashboard` | 31,480 stems = 26,480 + 5,000; 24 harvests; 2 farms, 4 lots, 8 varieties, 9 crops, 10 forecasts | PASS |
| GUI-22 | API → GUI: a variety created by a direct API request appears in the GUI; deleted from the GUI | (`POST /varieties` 201 outside the GUI), GUI `DELETE /varieties/205` 200 | listed as "205 GUIAUDIT_160718_ViaAPI Yellow"; after delete `GET` → 404 | PASS |
| GUI-23 | Delete a farm that still has a lot | `DELETE /farms/202` **409** | dialog shows "Cannot delete this farm: it is still referenced by 1 lot(s)…"; farm still exists | PASS |
| GUI-24 | Delete every test record, children first (2 forecasts, 4 harvests, crop, 2 seasons, lot, variety, farm) | 12 × `DELETE` 200 | each `GET` → 404 | PASS |
| GUI-25 | Only the test records changed | 36 writes logged, **0** outside the test ids | counts back to 1/3/7/8/3/20/8, 26,480 stems, forecast status Evaluated 1 / Pending 7 | PASS |
| GUI-26 | Browser-side secrets | – | no localStorage/sessionStorage keys, no JS-readable cookie; 401 without session; 403 for a write without the GUI header | PASS |
| GUI-27 | Forecast manual form: create (crop 1, Normal Production 2026, 2026-12-30), edit, delete | `POST /forecasts` 201, `PUT /forecasts/65` 200, `DELETE /forecasts/65` 200 | 1234.5 → 1300 and new method; after delete 404; forecasts back to 8 | PASS |
| GUI-28 | Empty state with active filters | `GET /harvests?date_from=2025-01-01&date_to=2025-01-02` | "No matching records — … Change or clear the filters." | PASS |
| GUI-29 | Loading state (varieties request delayed 1.5 s in the browser) | `GET /varieties` | "Loading data…", then 7 rows | PASS |
| GUI-30 | Error state (varieties request failed in the browser), then *Try again* | `GET /varieties` | "Could not load data — Cannot reach the server…", after retry 7 records | PASS |

Earlier the same day (before 10:54, with the bundle of the previous correction) the real system was also
checked for: harvest duplicate 409 (`real_02_harvest_duplicate_409.jpg`), forecast generation and
saving (`real_03_forecast_generated_saved.jpg`), delete refused 409 (`real_04_delete_refused_409.jpg`),
the dashboard (`real_01_dashboard.jpg`) and the phone layout (`real_05_mobile_forecasts.jpg`); after
the last correction all 10 navigable pages were reopened with bundle `index-CLqLDtTO.js`, each showing
the real counts with no error state.

## 3. Automated GUI tests

| Suite | Where | Result | Covers |
|---|---|---|---|
| Vitest + React Testing Library (60 tests, 5 files) | cloud workspace 11:03 and nobara-pc VM 11:05 | 60/60 both | pages, forms and validation rules (incl. the new harvest rules and filtered empty state), API client, components, utilities; `fetch` mocked inside tests only |
| Playwright, Chromium desktop + Pixel 7 (23 tests) | cloud, against the replica API + MySQL | 23/23 (11:03) | sign-in/out, key never in storage/HTML/scripts, every list page equals the DB, analysis, filters, narrow window, workflows A–D (variety CRUD, crop, harvest incl. out-of-season refusal, forecast generate/save/display), clean-up through the GUI, phone layout |
| axe-core 4.14.1 (WCAG 2 A/AA) on 11 views | cloud replica | 0 violations (11:04) | login, dashboard, analysis, 7 entity pages, harvest form with errors |

Playwright could not be run against the real system: Node.js is not installed on nobara-pc itself and
the desktop app's Linux VM cannot reach the host's `127.0.0.1:7003`. The real-system workflow above
replaces it; the automated E2E evidence is from the replica.

## 4. GUI completion

Denominator — capabilities required by the project and verified **on the real system**:

| Group | Items | Verified |
|---|---|---:|
| Screens reachable and showing real data | Login, Dashboard, Production analysis, Farms, Lots, Rose varieties, Crops, Seasons, Harvests, Forecasts | 10 / 10 |
| CRUD through the GUI | 7 entities × (create, list/read, update, delete) — Farm, Lot, Variety, Season, Crop, Harvest (GUI-01…14, 24); Forecast create (GUI-16/17/27), read (GUI-18), update (GUI-27), delete (GUI-24/27) | 28 / 28 |
| Integrated behaviour | client validation; API errors displayed; forecast generate → save → evaluate; historical filters by date, variety, lot and season; statistics and dashboard from the DB; API → GUI consistency; loading/empty/error states; session security in the browser | 8 / 8 |
| **Total** | | **46 / 46** |

**GUI completion = 46 / 46 × 100 = 100 %.**

## 5. Limitations

- Persistence during the GUI run was confirmed through independent API reads, not by a SQL client:
  the audit shell cannot reach the host's MySQL port. The same endpoints were verified with direct
  SQL read-back by the host harness (`API_CRUD_TEST_MATRIX.md`).
- Controls were operated with DOM events, not OS-level mouse/keyboard input; Playwright (replica)
  exercises the same workflows with real browser input.
- GUI-29/GUI-30 simulate a slow/failed network inside the browser for one endpoint; the API was not
  stopped.
- The browser pane is a desktop-width window (685 px in this session); the phone layout was checked
  with Playwright (Pixel 7) and with the pane's mobile preset earlier.
