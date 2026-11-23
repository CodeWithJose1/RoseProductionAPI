# REST API

Base URL: `http://127.0.0.1:7003` · JSON in, JSON out · Flask (`python app.py`).

The examples below were produced against a copy of `RoseProductionDB` loaded from the
2026-11-22 backup; ids and values match the real data at that date.

## 1. Authentication

Every endpoint except `/`, `/auth/*` and the GUI files (`/app/…`) is protected. Two ways to
authenticate:

| Client | Mechanism |
|---|---|
| Scripts, curl, Postman | Header `X-API-Key: <API_KEY from .env>` (original mechanism, unchanged) |
| The React GUI | `POST /auth/login` once with the key → signed **HttpOnly, SameSite=Strict** session cookie (`rose_session`, 8 h). The key is not stored in the browser. Writes must also send `X-Requested-With: RoseProductionGUI` (CSRF protection). |

| Situation | Status | Body |
|---|---|---|
| No key and no session | 401 | `{"error": "Unauthorized"}` |
| Wrong key | 401 | `{"error": "Unauthorized"}` |
| `API_KEY` missing in `.env` | 503 | `{"error": "API authentication is not configured"}` |
| Session write without the GUI header | 403 | `{"error": "Forbidden: …", "code": "CSRF_CHECK_FAILED"}` |
| 5 failed logins in 5 minutes (same IP) | 429 | `{"error": "Too many failed attempts…", "code": "TOO_MANY_ATTEMPTS"}` + `Retry-After` |

```bash
export KEY=...   # value of API_KEY in .env (never commit it)
curl -s http://127.0.0.1:7003/farms -H "X-API-Key: $KEY"
```

### Auth endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/login` | `{"api_key": "…"}` | `200 {"authenticated": true, "session_hours": 8.0}` · 400 · 401 · 429 |
| POST | `/auth/logout` | – | `200 {"authenticated": false}` |
| GET | `/auth/status` | – | `200 {"authenticated": false, "auth_configured": true}` |

## 2. Conventions

- **Status codes**: `200` OK · `201` created · `400` validation/business rule · `401` · `403` ·
  `404` not found · `405` method not allowed (e.g. `PATCH`: updates use `PUT`) · `409` conflict
  (duplicate, record in use) · `413` body larger than 1 MiB · `429` · `500` · `503` database unavailable.
- **Errors** always have the form below. `error` is a readable sentence (kept as a plain string, as in
  the original API); `code` and `details` (one message per field) are added when useful.

```json
{"error": "Validation failed", "code": "VALIDATION_ERROR",
 "details": {"quantity": "must be greater than zero"}}
```

- **Lists** keep the original shape `{"count": N, "<resource>": [...]}`; **single records**
  are returned as `{"<resource>": {...}}`; create/update add `"message"`; delete returns
  `{"message": "...", "deleted_<resource>": {"<id>": n}}`.
- **Validation**: strings are trimmed, must not be empty and respect the column length; ids must be
  positive integers that exist; dates are `YYYY-MM-DD`; decimals are rounded half-up to 2 places.
  A `PUT` replaces the record and needs all fields.
- **Transactions**: every write is one transaction; any database error rolls it back.
- Responses carry `Cache-Control: no-store`, `X-Content-Type-Options`, `X-Frame-Options` and a
  Content-Security-Policy. CORS is not enabled.

### Error codes

| code | Status | Cause |
|---|---|---|
| `INVALID_JSON` | 400 | body is not a JSON object |
| `VALIDATION_ERROR` | 400 | missing/invalid field (see `details`), bad filter, end date before start |
| `FOREIGN_KEY_NOT_FOUND` | 400 | referenced farm/lot/variety/crop/season does not exist (MySQL 1452) |
| `DATE_OUTSIDE_SEASON` | 400 | harvest/forecast date outside the selected season |
| `DATE_BEFORE_PLANTING` | 400 | harvest/forecast date earlier than the crop's `planting_date` (final audit, API rule) |
| `FUTURE_HARVEST_DATE` | 400 | harvest date later than today (final audit, API rule) |
| `DATABASE_RULE_VIOLATION` | 400 | a trigger refused the row (MySQL 1644) — trigger message returned |
| `CHECK_CONSTRAINT_VIOLATION` | 400 | a CHECK constraint refused the row (MySQL 3819) |
| `INSUFFICIENT_HISTORY` | 400 | fewer earlier harvests than the moving-average window |
| `NOT_FOUND` | 404 | record id does not exist |
| `RECORD_IN_USE` | 409 | delete refused: dependent rows exist (MySQL 1451) |
| `DUPLICATE_RECORD` | 409 | the record already exists — farm (name + location), lot (name in its farm), variety (name), crop (lot + variety + planting date), season (name with an overlapping period), harvest (crop + day), forecast (crop + date). See "Duplicate prevention" below |
| `CONCURRENT_UPDATE` | 409 | the database aborted the transaction because of a concurrent write (deadlock); nothing was written — retry |
| `PLANTING_DATE_CONFLICT` | 409 | a crop's planting date cannot move after its existing harvests/forecasts (final audit) |
| `REQUEST_ENTITY_TOO_LARGE` | 413 | request body above 1 MiB (`MAX_CONTENT_LENGTH`) |
| `SEASON_RANGE_CONFLICT` | 409 | new season dates would leave harvests/forecasts outside the season |
| `DATABASE_UNAVAILABLE` | 503 | MySQL cannot be reached |

### Duplicate prevention (since 1.2.0, 2026-11-23)

Every `POST` and `PUT` checks whether an equivalent record exists before writing:

| Resource | Same record when… | Field in `details` | Database key |
|---|---|---|---|
| Farm | same name **and** location | `name` | `unique_farm_name_location` |
| Lot | same name in the same farm | `name` | `unique_lot_farm_name` |
| RoseVariety | same name (any colour) | `name` | – (API only) |
| Crop | same lot, variety and planting date | `planting_date` | – (API only) |
| Season | same name with an overlapping period | `name` | `unique_season_name_dates` (exact dates) |
| Harvest | same crop and day | `harvest_date` | `unique_harvest_crop_date` |
| Forecast | same crop and date | `forecast_date` | `unique_crop_forecast_date` |

- Text fields (names, location, colour) are stored trimmed with internal spaces collapsed; comparisons
  ignore case and extra spaces.
- A `PUT` that keeps the record's own identifying values is always accepted; taking another record's
  values is refused. A refused request writes nothing and never answers 201.
- Concurrent identical requests are serialized with a row lock, so exactly one succeeds and the
  others receive 409 (verified with 8 parallel requests per resource).
- `POST /forecasts/generate` with `save: false` also returns `existing_forecast_id` (or `null`);
  saving a forecast for a crop/date that already has one is refused (409) and the stored forecast is
  not overwritten.

Example: `POST /varieties {"name": " quicksand ", "color": "Red"}` →
`409 {"error": "A rose variety with this name already exists: 'Quicksand' (Peach, variety #6)", "code": "DUPLICATE_RECORD", "details": {"name": "A rose variety with this name already exists"}}`

## 3. CRUD coverage

| Resource | List | Get by id | Create | Update | Delete | Filters on list |
|---|---|---|---|---|---|---|
| Farm `/farms` | ✔ (orig.) | ✔ new | ✔ new | ✔ new | ✔ new (409 if it has lots) | – |
| Lot `/lots` | ✔ (orig.) | ✔ new | ✔ new | ✔ new | ✔ new (409 if it has crops) | `farm_id` |
| RoseVariety `/varieties` | ✔ (orig.) | ✔ new | ✔ (orig.) | ✔ (orig.) | ✔ (orig., now 409 if it has crops) | – |
| Crop `/crops` | ✔ (orig.) | ✔ new | ✔ new | ✔ new | ✔ new (409 if harvests/forecasts) | `lot_id`, `variety_id` |
| Season `/seasons` | ✔ (orig.) | ✔ new | ✔ new | ✔ new | ✔ new (409 if harvests/forecasts) | – |
| Harvest `/harvests` | ✔ (orig.) | ✔ new | ✔ new | ✔ new | ✔ new | `crop_id`, `season_id`, `variety_id`, `lot_id`, `date_from`, `date_to` |
| Forecast `/forecasts` | ✔ (orig.) | ✔ new | ✔ new | ✔ new | ✔ new | same as harvests |

"orig." = existed before this work; URLs and response keys were kept (new keys were only added).

## 4. Endpoints

### Home

`GET /` (public) → `200 {"message": "Rose Production API is running", "database": "RoseProductionDB", "gui": "/app/", "version": "1.2.0"}`

### Farms

| Method | Path | Body |
|---|---|---|
| GET | `/farms` | – |
| GET | `/farms/{farm_id}` | – (includes `lots` and `total_area`) |
| POST | `/farms` | `{"name": str ≤100, "location": str ≤150}` |
| PUT | `/farms/{farm_id}` | same as POST |
| DELETE | `/farms/{farm_id}` | – |

```bash
curl -s -X POST http://127.0.0.1:7003/farms -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"name":"North Farm","location":"Tabacundo"}'
```
```json
{"message": "Farm created successfully",
 "farm": {"farm_id": 2, "name": "North Farm", "location": "Tabacundo", "lot_count": 0}}
```

### Lots

Body: `{"farm_id": int, "name": str ≤100, "area": number > 0 (DECIMAL 10,2)}`.

`GET /lots/1`:
```json
{"lot": {"lot_id": 1, "name": "Lot A", "area": 2.5,
         "farm": {"farm_id": 1, "name": "Rose Paradise Farm"}, "farm_id": 1,
         "crop_count": 2, "crops": [{"crop_id": 1, "planting_date": "2026-01-10", "...": "..."}]}}
```

### Rose varieties

Body: `{"name": str ≤100, "color": str ≤50}` (duplicate names are allowed, as in the schema).

```bash
curl -s -X PUT http://127.0.0.1:7003/varieties/10 -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"name":"API_TEST_UPDATED","color":"Red"}'
```
```json
{"message": "Rose variety updated successfully",
 "variety": {"variety_id": 10, "name": "API_TEST_UPDATED", "color": "Red"}}
```

`DELETE /varieties/1` (Freedom has crops):
```json
{"error": "Cannot delete this rose variety: it is still referenced by 2 crop(s). Delete or reassign those records first.",
 "code": "RECORD_IN_USE"}
```

### Crops

Body: `{"lot_id": int, "variety_id": int, "planting_date": "YYYY-MM-DD"}`. A `PUT` that moves the planting
date after existing harvests/forecasts of the crop is refused with 409 `PLANTING_DATE_CONFLICT`.
List items contain `lot`, `variety`, `lot_id`, `variety_id`, `label` (e.g. `"#1 · Freedom · Lot A"`),
`harvest_count`, `forecast_count`; `GET /crops/{id}` adds `total_harvested`.

### Seasons

Body: `{"name": str ≤100, "start_date": date, "end_date": date ≥ start_date}`.
Items include `duration_days`, `harvest_count`, `forecast_count`.

### Harvests

Body: `{"crop_id": int, "season_id": int, "harvest_date": date inside the season, "quantity": int > 0}`.

Rules checked by the API on `POST` and `PUT` (added in the final audit; the schema itself does not
enforce the last three):

| Rule | Refusal |
|---|---|
| date inside the selected season (also enforced by the triggers) | 400 `DATE_OUTSIDE_SEASON` |
| date not before the crop's `planting_date` | 400 `DATE_BEFORE_PLANTING` |
| date not later than today | 400 `FUTURE_HARVEST_DATE` |
| one harvest per crop and day (a `PUT` may keep its own date) | 409 `DUPLICATE_RECORD` |

The one-per-day rule protects `vw_forecast_status`/`vw_forecast_summary`, which join a forecast with
the harvest of the same crop and date: two harvests on that day would duplicate the forecast row and
distort MAE/MAPE (demonstrated in `docs/final-audit/evidence`, check NFR-02-20). Rows written
directly with SQL bypass these API rules.

`GET /harvests?variety_id=1&date_from=2026-02-08`:
```json
{"count": 2, "total_quantity": 3100, "harvests": [
  {"harvest_id": 19, "harvest_date": "2026-02-09", "quantity": 1600,
   "crop": {"crop_id": 1, "variety": "Freedom", "lot": "Lot A", "variety_id": 1, "lot_id": 1, "color": "Green"},
   "season": {"season_id": 1, "name": "Valentines Day 2026"}, "crop_id": 1, "season_id": 1},
  {"harvest_id": 20, "harvest_date": "2026-02-11", "quantity": 1500, "...": "..."}]}
```

`POST /harvests` with `{"crop_id":1,"season_id":1,"harvest_date":"2026-03-01","quantity":10}` → 400:
```json
{"error": "The harvest date 2026-03-01 is outside the season 'Valentines Day 2026' (2026-02-01 to 2026-02-14)",
 "code": "DATE_OUTSIDE_SEASON", "details": {"harvest_date": "must be between 2026-02-01 and 2026-02-14"}}
```

### Forecasts

Body: `{"crop_id": int, "season_id": int, "forecast_date": date inside the season and not before the
crop's planting date, "estimated_quantity": number ≥ 0, "method": str ≤100}`. Each forecast in `GET /forecasts` and
`GET /forecasts/{id}` carries an `evaluation` object = its row of `vw_forecast_status`:

```json
{"forecast": {"forecast_id": 1, "forecast_date": "2026-02-09", "estimated_quantity": 1550.0,
  "method": "Moving Average (3 records)", "crop": {"crop_id": 1, "variety": "Freedom", "...": "..."},
  "season": {"season_id": 1, "name": "Valentines Day 2026"}, "crop_id": 1, "season_id": 1,
  "evaluation": {"actual_quantity": 1600, "forecast_status": "Evaluated", "absolute_error": 50.0, "...": "..."}}}
```

| Method | Path | Description |
|---|---|---|
| GET | `/forecasts/status` | all rows of `vw_forecast_status` |
| GET | `/forecasts/summary` | `{"view": "vw_forecast_summary", "rows": [{"total_forecasts": 7, "evaluated_forecasts": 1, "pending_forecasts": 6, "MAE": 50.0, "MAPE": 3.13}]}` |
| POST | `/forecasts/generate` | moving-average estimate (see below) |

#### Forecast generation — `POST /forecasts/generate`

```json
{"crop_id": 1, "season_id": 1, "forecast_date": "2026-02-12", "window": 3, "save": false}
```

`window` (1–12, default 3) and `save` (default `false`) are optional. With `save: false` nothing is
written (200); with `save: true` the forecast is stored with method
`"Moving Average (N records)"` and returned (201).

```json
{"message": "Forecast estimate calculated",
 "calculation": {"estimated_quantity": 1550.0, "window": 3, "method": "Moving Average (3 records)",
   "formula": "(1500 + 1600 + 1550) / 3 = 1550.00",
   "history": [{"harvest_id": 20, "harvest_date": "2026-02-11", "quantity": 1500, "season": "Valentines Day 2026"},
               {"harvest_id": 19, "harvest_date": "2026-02-09", "quantity": 1600, "season": "Valentines Day 2026"},
               {"harvest_id": 3,  "harvest_date": "2026-02-07", "quantity": 1550, "season": "Valentines Day 2026"}],
   "crop_id": 1, "crop_label": "#1 · Freedom · Lot A", "season_id": 1, "season": "Valentines Day 2026",
   "forecast_date": "2026-02-12", "saved": false}}
```

**Method.** `estimate = (q₁ + … + q_N) / N`, where q₁…q_N are the quantities of the N most recent
harvests of the same crop with `harvest_date < forecast_date` (ties ordered by `harvest_id`),
rounded half-up to 2 decimals. Assumptions: only real `Harvest` rows are used; if fewer than N exist
the request is refused (`400 INSUFFICIENT_HISTORY`) rather than computed from a shorter history;
the method has no trend or seasonality term (baseline method). This procedure reproduces exactly the
7 forecasts already stored in the database (tested).

### Statistics

| Method | Path | Description |
|---|---|---|
| GET | `/stats/dashboard` | counts per table, total area, production total/avg/min/max, `by_variety`, `by_season`, `over_time` (per date), `upcoming_seasons`, `forecast_status`, `forecast_vs_actual` |
| GET | `/stats/production` | `group_by` = `variety`·`lot`·`season`·`crop`·`month`·`date` + the harvest filters |

`GET /stats/production?group_by=season`:
```json
{"group_by": "season", "filters": {},
 "overall": {"total": 26480, "average": 1324.0, "minimum": 1000, "maximum": 1600, "records": 20},
 "groups": [
   {"key": 1, "label": "Valentines Day 2026",    "total": 14930, "average": 1357.27, "minimum": 1100, "maximum": 1600, "records": 11},
   {"key": 2, "label": "Mothers Day 2026",       "total": 8400,  "average": 1400.0,  "minimum": 1300, "maximum": 1500, "records": 6},
   {"key": 3, "label": "Normal Production 2026", "total": 3150,  "average": 1050.0,  "minimum": 1000, "maximum": 1100, "records": 3}]}
```

### GUI files

| Path | Description |
|---|---|
| `GET /app` | redirects to `/app/` |
| `GET /app/` and `/app/<route>` | `frontend/dist/index.html` (single-page application) |
| `GET /app/assets/<file>` | built JS/CSS (long cache, content-hashed names) |

If `frontend/dist` is missing, `/app/` answers `503 GUI_NOT_BUILT`.

## 5. Implementation notes

- Code: `app.py` (factory, security headers), `auth.py`, `errors.py`, `validators.py`,
  `serializers.py`, `forecasting.py`, `routes/<resource>.py`.
- `models.py` was not modified; the models map the existing tables (`db.create_all()` is never called).
- The seven original GET handlers and the original variety POST/PUT/DELETE were moved from `app.py`
  into `routes/` with the same URLs, status codes, success messages and response keys
  (`tests/test_api_original_contract.py`).
