# Graphical User Interface

React 19 + Vite single-page application in `frontend/`. Flask serves the production build at
**http://127.0.0.1:7003/app/**. All data shown comes from the Flask API, which reads MySQL:

```
GUI (browser) → fetch /farms, /harvests… (session cookie) → Flask API → MySQL → JSON → GUI
```

Screenshots in `docs/screenshots/` were captured with `node frontend/scripts/screenshots.mjs`
against a copy of `RoseProductionDB` restored from the 2026-11-22 backup (same rows as the real
database on that date).

## 1. Screens

| # | Screen | Route | Purpose | Screenshot |
|---|---|---|---|---|
| 1 | Sign in | `/app/` (not signed in) | enter the access key (the `API_KEY`) once; it is exchanged for a session cookie | `01-login.png` |
| 2 | Dashboard | `/app/` | live KPIs and charts | `02-dashboard.png` |
| 3 | Farms | `/app/farms` | list, create, edit, delete; "View lots" shows the farm detail with its lots and total area | `03-farms.png` |
| 4 | Lots | `/app/lots` | CRUD, filter by farm, farm dropdown, area validation | `04-lots.png` |
| 5 | Rose varieties | `/app/varieties` | CRUD, colour swatch, crop count | `05-varieties.png` |
| 6 | Crops | `/app/crops` | CRUD with lot and variety dropdowns, filters by lot/variety | `06-crops.png` |
| 7 | Seasons | `/app/seasons` | CRUD, status (active/upcoming/past), date-range validation | `07-seasons.png` |
| 8 | Harvests | `/app/harvests` | CRUD, filters by date range, variety, lot, crop and season | `08-harvests.png`, `09-harvest-validation.png` |
| 9 | Forecasts | `/app/forecasts` | CRUD, filters, status/actual/error from `vw_forecast_status`, summary from `vw_forecast_summary`, **Generate forecast** wizard | `10-forecasts.png`, `11-forecast-generate.png` |
| 10 | Production analysis | `/app/analytics` | total/average/min/max grouped by variety, lot, season, crop, month or date with filters (FR-05, FR-06) | `12-analytics.png` |
| – | Phone layout | any | collapsible menu, stacked table rows | `13-mobile-dashboard.png`, `14-mobile-menu.png` |

## 2. Navigation and layout

- **Sidebar** grouped in *Overview* (Dashboard, Production analysis), *Farm structure* (Farms, Lots,
  Rose varieties, Crops) and *Production* (Seasons, Harvests, Forecasts). The active page is highlighted.
- **Top bar** with breadcrumb, connection indicator and *Sign out*.
- Under 900 px the sidebar becomes an off-canvas menu (☰ button); under 640 px tables are shown as
  label/value cards, form rows stack and dialogs open as bottom sheets.
- Browser routes (`/app/harvests`, …) can be bookmarked and reloaded; Flask returns the SPA for them.

## 3. Common components

| Component | Behaviour |
|---|---|
| `DataTable` | search box, sortable columns (click header: ascending → descending → off), 10 rows per page, record counter, empty state ("No matching records — change or clear the filters" when filters are active, "No … yet" otherwise) |
| `ResourceFormModal` | create/edit dialog; validates on submit and then live; maps API field errors (`details`) onto the fields; shows other API errors in a banner |
| `ConfirmDialog` | every delete asks for confirmation; if the API refuses (e.g. *still referenced by 2 crop(s)*), the reason is shown in the dialog |
| `LoadingState` / `EmptyState` / `ErrorState` | spinner while loading, explanatory empty states, error with **Try again** |
| Toasts | success notifications after create/update/delete; errors stay longer |
| `FilterBar` | filters in one row above the table, **Clear filters** |

## 4. Forms and validation

Client-side rules mirror the database (the API re-validates everything; the triggers and CHECK
constraints remain the final guard):

| Form | Fields | Rules shown to the user |
|---|---|---|
| Farm | name, location | required, ≤ 100 / ≤ 150 characters |
| Lot | farm (dropdown), name, area | farm required, area > 0 with 2 decimals |
| Variety | name, colour (suggestions) | required, ≤ 100 / ≤ 50 characters; duplicates allowed |
| Crop | lot (dropdown), variety (dropdown), planting date | all required, valid date |
| Season | name, start date, end date | end date ≥ start date |
| Harvest | crop, season, date, quantity | the date picker is limited to max(season start, planting date) … min(season end, today) and shows "Allowed: *min* to *max*"; dates before the crop's planting date or in the future are refused in the form and by the API; one record per crop and day (the API's 409 message is shown on the date field); "Quantity must be greater than zero"; whole numbers only. The table shows Variety, Lot, Crop (#id) and Season for every harvest |
| Forecast | crop, season, date, estimated quantity, method | date inside the season and not before the crop's planting date (manual form and Generate wizard); quantity ≥ 0; duplicate crop/date → API message *A forecast already exists for this crop on this date* |

Foreign keys are always chosen from dropdowns populated from the API (`/lots`, `/varieties`,
`/crops`, `/seasons`); users never type ids.

## 5. Dashboard

| Element | Source | Notes |
|---|---|---|
| KPI cards: farms, lots (+ total area), varieties, crops, harvests (+ seasons), total stems (+ avg/min/max), forecasts (+ evaluated/pending) | `GET /stats/dashboard` | counts are `COUNT(*)` of each table |
| Production by rose variety | `by_variety` | horizontal bars, sorted by total |
| Production by season | `by_season` | bars |
| Harvest quantities over time | `over_time` | one bar per harvest date (days without harvests are not drawn) |
| Forecast vs actual production | `forecast_vs_actual` (from `vw_forecast_status`) | only forecasts with a real harvest for the same crop and date are drawn; pending forecasts are listed separately and never shown as evaluated |
| Upcoming seasons | `upcoming_seasons` | active or future seasons, days until start |

Every chart has a **Table** toggle that shows the same numbers as a table (accessibility), an
empty state when there is no data, and hover tooltips. Colours: one validated categorical palette
(blue = actual/primary measure, orange = estimate); text never relies on colour alone.

## 6. Forecast generation wizard

1. **Generate forecast** on the Forecasts page.
2. Choose crop, season, forecast date (limited to the season) and N (default 3, as in the project).
3. **Calculate estimate** → `POST /forecasts/generate` with `save:false`: shows the estimate, the
   formula (e.g. `(1500 + 1600 + 1550) / 3 = 1550.00`) and the harvests used. Nothing is written.
4. **Save forecast** → same request with `save:true`; the dialog shows *Saved as forecast #N* and the
   list refreshes with the new forecast and its status (*Pending* until a real harvest exists for that
   crop and date).

If the crop has fewer than N earlier harvests the API message is shown and nothing is saved.

## 7. GUI ↔ API integration

- **One HTTP client** (`src/api/client.js`): same-origin `fetch` with `credentials: 'same-origin'`,
  JSON bodies, `X-Requested-With: RoseProductionGUI` on writes, conversion of error responses into
  `ApiError {status, message, code, details}`, readable default messages per status (0 network, 401,
  403, 404, 409, 429, 5xx, 503) and de-duplication of identical concurrent GET requests.
- `src/api/endpoints.js` describes each resource (`list/get/create/update/remove`) plus
  `forecasts.generate/status/summary`, `stats.dashboard/production` and `auth.*`.
- **401** anywhere → the session is considered expired and the sign-in screen is shown with a message.
- After every successful create/update/delete the list is re-fetched from the API, so the screen
  always reflects MySQL; a browser reload shows the same data.
- **No API key in the front-end**: not in source files, HTML, Vite variables, local/session storage or
  the bundle (checked by `tests/test_gui_and_secrets.py` and `e2e/auth.spec.js`). The key is typed by
  the operator at sign-in, sent once over the same-origin connection and discarded.
- No mock data is used by the application; mocks exist only inside unit tests.

## 8. Development

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173/app/ — Vite proxies API paths to Flask on :7003
npm run build      # writes frontend/dist, served by Flask at /app/
npm test           # Vitest + React Testing Library
npx playwright test   # end-to-end (Flask must be running)
```

Source layout:

```
frontend/src/
├── api/            client.js (HTTP), endpoints.js (resources)
├── context/        AuthContext (session), ToastContext
├── hooks/          useApi (loading/error/reload), useLookups (dropdown data)
├── components/     Layout, DataTable, CrudPage, ResourceFormModal, Modal/ConfirmDialog,
│                   FormField, Charts, Common (badges, filters, stat cards), States
├── pages/          Dashboard, Analytics, Farms, Lots, Varieties, Crops, Seasons, Harvests, Forecasts, Login
├── utils/          format.js, validation.js
└── __tests__/      Vitest suites
```

## Duplicate prevention (2026-11-23)

- **One submission at a time.** Create/edit dialogs, the delete confirmation and the forecast wizard
  use a synchronous lock: a second click, Enter or programmatic submit while a request is pending is
  ignored; the button shows a spinner and is disabled.
- **Immediate hints.** Each form checks the rows already loaded on the page with the same rules as the
  API (case and extra spaces ignored) and shows, without sending a request: "A rose variety with this
  name already exists.", "This lot already exists in the selected farm.", "A farm with this name
  already exists at this location.", "A season with this name already exists for an overlapping
  period.", "This variety is already planted in this lot on this date.", "This crop already has a
  harvest on this date. Edit that record instead.", "This forecast already exists for the selected crop
  and date.". Editing a record without changing its identifying values is always allowed.
- **API refusals.** If the API answers 409 (e.g. someone else created the record meanwhile), the dialog
  stays open, keeps the typed values, shows the API message as a banner and on the field, and no success
  message appears.
- **Forecast wizard.** When the preview reports an existing forecast for that crop and date, a warning
  is shown and **Save forecast** is disabled.

## Final audit

The GUI was re-verified on the real system on 2026-11-22 (bundle `index-CLqLDtTO.js`): 30 steps
covering create/edit/delete of every entity, validation, the forecasting workflow, filters, statistics
and API↔GUI consistency. See `docs/final-audit/GUI_INTEGRATION_TEST_REPORT.md`.
