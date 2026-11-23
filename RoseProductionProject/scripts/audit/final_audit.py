#!/usr/bin/env python3
"""Independent final-audit harness for the Rose Production system.

Runs against the REAL running API (default http://127.0.0.1:7003) over HTTP
and against the database configured in .env (read with the project's own
config.py), and writes machine-readable evidence to
docs/final-audit/evidence/audit_results.json (+ a text log).

What it does
  1. environment and schema inventory (information_schema), compared with
     the SQLAlchemy models
  2. read-only data-quality checks
  3. NFR-01 timings (SQL + HTTP) with EXPLAIN / EXPLAIN ANALYZE
  4. NFR-02 constraint/trigger tests inside a transaction that is ALWAYS
     rolled back
  5. NFR-06 authentication / access-control tests (no key, wrong key,
     session + CSRF header, CORS, injection probes, key exposure)
  6. full CRUD matrix for the 7 entities over HTTP, each step verified with
     SQL (database effect)
  7. FR-01 ... FR-09 functional checks with isolated AUDIT_ records
  8. NFR-05 extensibility (schema fingerprint before/after)
  9. clean-up of exactly the ids it created, then a guard that every
     pre-existing row and the schema are unchanged

Safety: it never updates or deletes a row it did not create; it never runs
DDL. Secrets from .env are used but never printed or written.

Usage (from the project root, virtualenv active, API running):
    python scripts/audit/final_audit.py
"""

import datetime as dt
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text  # noqa
from sqlalchemy.exc import DBAPIError  # noqa

from config import Config  # noqa
import models  # noqa

BASE = os.environ.get("ROSE_BASE_URL", "http://127.0.0.1:7003").rstrip("/")
KEY = Config.API_KEY
OUT_DIR = os.environ.get("AUDIT_OUT_DIR") or os.path.join(
    ROOT, "docs", "final-audit", "evidence")
RUN_ID = uuid.uuid4().hex[:8]
TAG = f"AUDIT_{RUN_ID}"
TODAY = dt.date.today()
PAST_YEAR = 2001            # isolated past season for test harvests
FUTURE_YEAR = 2097          # isolated future season for future forecasts
TABLES = {"Farm": "farm_id", "Lot": "lot_id", "RoseVariety": "variety_id",
          "Crop": "crop_id", "Season": "season_id",
          "Harvest": "harvest_id", "Forecast": "forecast_id"}
DELETE_ORDER = ["Forecast", "Harvest", "Crop", "Season", "Lot",
                "RoseVariety", "Farm"]

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI,
                       pool_pre_ping=True)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

RESULTS = {
    "run_id": RUN_ID,
    "started_at": dt.datetime.now().astimezone().isoformat(),
    "base_url": BASE,
    "sections": {},
    "checks": [],
}
CREATED = {t: [] for t in TABLES}
LOG_LINES = []


def log(message):
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {message}"
    LOG_LINES.append(line)
    print(line, flush=True)


def redact(value):
    """Never let the API key or DB password reach the evidence files."""
    textual = json.dumps(value, default=str) if not isinstance(
        value, str) else value
    for secret in (KEY, os.getenv("DB_PASSWORD")):
        if secret and len(secret) >= 4:
            textual = textual.replace(secret, "<redacted>")
    return textual if isinstance(value, str) else json.loads(textual)


def check(section, check_id, title, expected, actual, passed, **extra):
    item = {"section": section, "id": check_id, "title": title,
            "expected": expected, "actual": actual,
            "result": "PASS" if passed else "FAIL"}
    item.update(extra)
    RESULTS["checks"].append(redact(item))
    log(f"{item['result']:4} {section} {check_id} {title} -> {actual}")
    return passed


def finding(section, check_id, title, actual, severity, **extra):
    """A data-quality observation that is not a pass/fail test."""
    item = {"section": section, "id": check_id, "title": title,
            "expected": "none", "actual": actual, "result": "FINDING",
            "severity": severity}
    item.update(extra)
    RESULTS["checks"].append(redact(item))
    log(f"FIND {section} {check_id} {title} -> {actual}")


# ----------------------------------------------------------------------
# HTTP helpers
# ----------------------------------------------------------------------

def http(method, path, body=None, key="default", headers=None, raw=None,
         opener=None):
    url = BASE + path
    data = raw if raw is not None else (
        json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(url, data=data, method=method)
    if key == "default":
        key = KEY
    if key is not None:
        request.add_header("X-API-Key", key)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    start = time.perf_counter()
    try:
        response = (opener or OPENER).open(request, timeout=60)
        status, payload, hdrs = response.status, response.read(), \
            dict(response.headers)
    except urllib.error.HTTPError as error:
        status, payload, hdrs = error.code, error.read(), dict(error.headers)
    elapsed = (time.perf_counter() - start) * 1000
    try:
        parsed = json.loads(payload) if payload else None
    except ValueError:
        parsed = None
    return status, parsed, elapsed, hdrs, payload


def sql(query, **params):
    with engine.connect() as conn:
        return conn.execute(text(query), params).mappings().all()


def sql_one(query, **params):
    rows = sql(query, **params)
    return dict(rows[0]) if rows else None


def jsonable(row):
    return {k: (v.isoformat() if hasattr(v, "isoformat") else
                float(v) if v.__class__.__name__ == "Decimal" else v)
            for k, v in dict(row).items()}


# ----------------------------------------------------------------------
# Snapshots
# ----------------------------------------------------------------------

def data_snapshot():
    snap = {}
    with engine.connect() as conn:
        for table, pk in TABLES.items():
            rows = conn.execute(text(f"SELECT * FROM `{table}`")).mappings()
            snap[table] = {
                row[pk]: hashlib.sha256(json.dumps(
                    jsonable(row), sort_keys=True).encode()).hexdigest()
                for row in rows}
    return snap


def schema_fingerprint():
    queries = [
        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
        "COLUMN_KEY, EXTRA FROM information_schema.COLUMNS WHERE "
        "TABLE_SCHEMA = DATABASE() ORDER BY 1, 2",
        "SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE FROM "
        "information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = "
        "DATABASE() ORDER BY 1, 2",
        "SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME FROM "
        "information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
        "ORDER BY 1, 2, 3",
        "SELECT TRIGGER_NAME, EVENT_MANIPULATION, ACTION_TIMING, "
        "ACTION_STATEMENT FROM information_schema.TRIGGERS WHERE "
        "TRIGGER_SCHEMA = DATABASE() ORDER BY 1",
        "SELECT TABLE_NAME, VIEW_DEFINITION FROM information_schema.VIEWS "
        "WHERE TABLE_SCHEMA = DATABASE() ORDER BY 1",
        "SELECT ROUTINE_NAME, ROUTINE_DEFINITION FROM "
        "information_schema.ROUTINES WHERE ROUTINE_SCHEMA = DATABASE() "
        "ORDER BY 1",
    ]
    digest = hashlib.sha256()
    for query in queries:
        for row in sql(query):
            digest.update(json.dumps(jsonable(row), sort_keys=True,
                                     default=str).encode())
    return digest.hexdigest()


# ----------------------------------------------------------------------
# 1. Environment and schema inventory
# ----------------------------------------------------------------------

def section_environment():
    import flask
    import pymysql
    import sqlalchemy
    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "flask": flask.__version__ if hasattr(flask, "__version__") else
        __import__("importlib.metadata").metadata.version("flask"),
        "flask_sqlalchemy": __import__("importlib.metadata").metadata
        .version("flask-sqlalchemy"),
        "sqlalchemy": sqlalchemy.__version__,
        "pymysql": pymysql.__version__ if hasattr(pymysql, "__version__")
        else "?",
        "mysql_version": sql_one("SELECT VERSION() AS v")["v"],
        "database": sql_one("SELECT DATABASE() AS d")["d"],
        "sql_mode": sql_one("SELECT @@SESSION.sql_mode AS m")["m"],
        "audit_date": TODAY.isoformat(),
    }
    try:
        fmt = ("{{json .Config.Image}}|{{json .State.Status}}|"
               "{{json .HostConfig.PortBindings}}|{{json .Mounts}}|"
               "{{json .HostConfig.RestartPolicy}}")
        out = subprocess.run(["docker", "inspect", "Mysqlcontainer",
                              "--format", fmt], capture_output=True,
                             text=True, timeout=20)
        if out.returncode == 0:
            image, state, ports, mounts, restart = out.stdout.strip().split(
                "|", 4)
            env["docker"] = {
                "image": json.loads(image), "state": json.loads(state),
                "port_bindings": json.loads(ports),
                "mounts": [{k: m.get(k) for k in ("Type", "Name", "Source",
                                                  "Destination")}
                           for m in json.loads(mounts)],
                "restart_policy": json.loads(restart),
            }
        else:
            env["docker"] = {"error": out.stderr.strip()[:300]}
    except Exception as exc:  # docker not available here
        env["docker"] = {"error": str(exc)[:300]}
    status, body, ms, _, _ = http("GET", "/", key=None)
    env["api_home"] = {"status": status, "body": body,
                       "ms": round(ms, 1)}
    RESULTS["sections"]["environment"] = env
    check("ENV", "ENV-01", "API reachable and public home endpoint",
          200, status, status == 200)
    check("ENV", "ENV-02", "API runs the audited code version",
          "1.2.0", (body or {}).get("version"),
          (body or {}).get("version") == "1.2.0")
    check("ENV", "ENV-03", "Backend connected to MySQL 8 RoseProductionDB",
          "8.x / RoseProductionDB",
          f"{env['mysql_version']} / {env['database']}",
          env["mysql_version"].startswith("8.")
          and env["database"] == "RoseProductionDB")


def section_schema():
    inv = {}
    inv["tables"] = [jsonable(r) for r in sql(
        "SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_COLLATION, TABLE_ROWS "
        "FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
        "ORDER BY TABLE_TYPE, TABLE_NAME")]
    inv["columns"] = [jsonable(r) for r in sql(
        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
        "COLUMN_KEY, EXTRA FROM information_schema.COLUMNS WHERE "
        "TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN "
        "('Farm','Lot','RoseVariety','Crop','Season','Harvest','Forecast')"
        " ORDER BY TABLE_NAME, ORDINAL_POSITION")]
    inv["constraints"] = [jsonable(r) for r in sql(
        "SELECT tc.TABLE_NAME, tc.CONSTRAINT_NAME, tc.CONSTRAINT_TYPE, "
        "cc.CHECK_CLAUSE, rc.UPDATE_RULE, rc.DELETE_RULE, "
        "rc.REFERENCED_TABLE_NAME FROM information_schema.TABLE_CONSTRAINTS"
        " tc LEFT JOIN information_schema.CHECK_CONSTRAINTS cc ON "
        "cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA AND cc.CONSTRAINT_NAME"
        " = tc.CONSTRAINT_NAME LEFT JOIN "
        "information_schema.REFERENTIAL_CONSTRAINTS rc ON "
        "rc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA AND rc.CONSTRAINT_NAME"
        " = tc.CONSTRAINT_NAME WHERE tc.CONSTRAINT_SCHEMA = DATABASE() "
        "ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME")]
    inv["foreign_keys"] = [jsonable(r) for r in sql(
        "SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME, "
        "REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME FROM "
        "information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = "
        "DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY 1, 2")]
    inv["indexes"] = [jsonable(r) for r in sql(
        "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, "
        "COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA "
        "= DATABASE() ORDER BY 1, 2, 4")]
    inv["triggers"] = [jsonable(r) for r in sql(
        "SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, EVENT_MANIPULATION, "
        "ACTION_TIMING FROM information_schema.TRIGGERS WHERE "
        "TRIGGER_SCHEMA = DATABASE() ORDER BY 1")]
    inv["views"] = [jsonable(r) for r in sql(
        "SELECT TABLE_NAME, VIEW_DEFINITION FROM information_schema.VIEWS "
        "WHERE TABLE_SCHEMA = DATABASE() ORDER BY 1")]
    inv["routines"] = [jsonable(r) for r in sql(
        "SELECT ROUTINE_NAME, ROUTINE_TYPE FROM information_schema.ROUTINES"
        " WHERE ROUTINE_SCHEMA = DATABASE() ORDER BY 1")]
    inv["row_counts"] = {t: sql_one(f"SELECT COUNT(*) AS n FROM `{t}`")["n"]
                         for t in TABLES}
    inv["schema_fingerprint"] = schema_fingerprint()
    RESULTS["sections"]["schema"] = inv

    base_tables = {t["TABLE_NAME"] for t in inv["tables"]
                   if t["TABLE_TYPE"] == "BASE TABLE"}
    views = {v["TABLE_NAME"] for v in inv["views"]}
    check("SCHEMA", "SCH-01", "Seven entity tables exist (InnoDB)",
          sorted(TABLES), sorted(base_tables & set(TABLES)),
          set(TABLES) <= base_tables and all(
              t["ENGINE"] == "InnoDB" for t in inv["tables"]
              if t["TABLE_NAME"] in TABLES))
    check("SCHEMA", "SCH-02", "Both views exist",
          ["vw_forecast_status", "vw_forecast_summary"], sorted(views),
          {"vw_forecast_status", "vw_forecast_summary"} <= views)

    # --- compare with the SQLAlchemy models --------------------------
    db_cols = {}
    for c in inv["columns"]:
        db_cols.setdefault(c["TABLE_NAME"], {})[c["COLUMN_NAME"]] = c
    mismatches = []
    model_by_table = {m.__tablename__: m for m in (
        models.Farm, models.Lot, models.RoseVariety, models.Crop,
        models.Season, models.Harvest, models.Forecast)}
    db_fks = {(f["TABLE_NAME"], f["COLUMN_NAME"]):
              (f["REFERENCED_TABLE_NAME"], f["REFERENCED_COLUMN_NAME"])
              for f in inv["foreign_keys"]}
    for table, model in model_by_table.items():
        mapper_cols = model.__table__.columns
        if set(c.name for c in mapper_cols) != set(db_cols.get(table, {})):
            mismatches.append(f"{table}: column set differs "
                              f"model={sorted(c.name for c in mapper_cols)} "
                              f"db={sorted(db_cols.get(table, {}))}")
            continue
        for col in mapper_cols:
            dbc = db_cols[table][col.name]
            if (dbc["IS_NULLABLE"] == "YES") != bool(col.nullable):
                mismatches.append(f"{table}.{col.name}: nullable model="
                                  f"{col.nullable} db={dbc['IS_NULLABLE']}")
            model_type = str(col.type.compile(
                dialect=engine.dialect)).lower()
            db_type = dbc["COLUMN_TYPE"].lower()
            norm = {"integer": "int"}.get(model_type, model_type)
            norm = norm.replace("numeric", "decimal").replace(" ", "")
            if not db_type.replace(" ", "").startswith(norm):
                mismatches.append(f"{table}.{col.name}: type model="
                                  f"{model_type} db={db_type}")
            if col.primary_key != (dbc["COLUMN_KEY"] == "PRI"):
                mismatches.append(f"{table}.{col.name}: PK differs")
            for fk in col.foreign_keys:
                target = (fk.column.table.name, fk.column.name)
                if db_fks.get((table, col.name)) != target:
                    mismatches.append(f"{table}.{col.name}: FK model="
                                      f"{target} db="
                                      f"{db_fks.get((table, col.name))}")
        model_fk_cols = {c.name for c in mapper_cols if c.foreign_keys}
        db_fk_cols = {col for (t, col) in db_fks if t == table}
        if model_fk_cols != db_fk_cols:
            mismatches.append(f"{table}: FK columns model="
                              f"{sorted(model_fk_cols)} db="
                              f"{sorted(db_fk_cols)}")
    names = {c["CONSTRAINT_NAME"] for c in inv["constraints"]}
    for model in model_by_table.values():
        for constraint in model.__table__.constraints:
            if constraint.name and constraint.name not in names \
                    and constraint.__class__.__name__ in (
                        "CheckConstraint", "UniqueConstraint"):
                mismatches.append(f"{model.__tablename__}: constraint "
                                  f"{constraint.name} not in DB")
        for index in model.__table__.indexes:
            if index.name not in {i["INDEX_NAME"] for i in inv["indexes"]}:
                mismatches.append(f"index {index.name} not in DB")
    check("SCHEMA", "SCH-03", "SQLAlchemy models match the MySQL schema "
          "(columns, types, nullability, PK, FK, named constraints, index)",
          "no mismatch", mismatches or "no mismatch", not mismatches)


# ----------------------------------------------------------------------
# 2. Data quality (read-only)
# ----------------------------------------------------------------------

def section_data_quality():
    orphan_sql = {
        "Lot->Farm": "SELECT COUNT(*) n FROM Lot l LEFT JOIN Farm f ON "
                     "f.farm_id=l.farm_id WHERE f.farm_id IS NULL",
        "Crop->Lot": "SELECT COUNT(*) n FROM Crop c LEFT JOIN Lot l ON "
                     "l.lot_id=c.lot_id WHERE l.lot_id IS NULL",
        "Crop->RoseVariety": "SELECT COUNT(*) n FROM Crop c LEFT JOIN "
                             "RoseVariety v ON v.variety_id=c.variety_id "
                             "WHERE v.variety_id IS NULL",
        "Harvest->Crop": "SELECT COUNT(*) n FROM Harvest h LEFT JOIN Crop c "
                         "ON c.crop_id=h.crop_id WHERE c.crop_id IS NULL",
        "Harvest->Season": "SELECT COUNT(*) n FROM Harvest h LEFT JOIN "
                           "Season s ON s.season_id=h.season_id WHERE "
                           "s.season_id IS NULL",
        "Forecast->Crop": "SELECT COUNT(*) n FROM Forecast f LEFT JOIN Crop "
                          "c ON c.crop_id=f.crop_id WHERE c.crop_id IS NULL",
        "Forecast->Season": "SELECT COUNT(*) n FROM Forecast f LEFT JOIN "
                            "Season s ON s.season_id=f.season_id WHERE "
                            "s.season_id IS NULL",
    }
    total_orphans = {k: sql_one(q)["n"] for k, q in orphan_sql.items()}
    check("DATA", "DQ-01", "No orphan rows in the 7 relationships", 0,
          total_orphans, sum(total_orphans.values()) == 0)
    rules = {
        "harvest quantity <= 0": "SELECT COUNT(*) n FROM Harvest WHERE "
                                 "quantity <= 0",
        "forecast estimate < 0": "SELECT COUNT(*) n FROM Forecast WHERE "
                                 "estimated_quantity < 0",
        "season end < start": "SELECT COUNT(*) n FROM Season WHERE "
                              "end_date < start_date",
        "harvest outside its season": "SELECT COUNT(*) n FROM Harvest h "
                                      "JOIN Season s USING (season_id) WHERE"
                                      " h.harvest_date NOT BETWEEN "
                                      "s.start_date AND s.end_date",
        "forecast outside its season": "SELECT COUNT(*) n FROM Forecast f "
                                       "JOIN Season s USING (season_id) "
                                       "WHERE f.forecast_date NOT BETWEEN "
                                       "s.start_date AND s.end_date",
    }
    db_rules = {k: sql_one(q)["n"] for k, q in rules.items()}
    check("DATA", "DQ-02", "Existing rows satisfy the database rules", 0,
          db_rules, sum(db_rules.values()) == 0)

    before_planting = [jsonable(r) for r in sql(
        "SELECT h.harvest_id, h.crop_id, c.planting_date, h.harvest_date "
        "FROM Harvest h JOIN Crop c USING (crop_id) WHERE h.harvest_date < "
        "c.planting_date ORDER BY h.harvest_id")]
    finding("DATA", "DQ-03", "Harvests dated before their crop's planting "
            "date (not prevented by the schema)", before_planting or "none",
            "MEDIUM" if before_planting else "NONE")
    forecast_before = [jsonable(r) for r in sql(
        "SELECT f.forecast_id, f.crop_id, c.planting_date, f.forecast_date "
        "FROM Forecast f JOIN Crop c USING (crop_id) WHERE f.forecast_date "
        "< c.planting_date ORDER BY f.forecast_id")]
    finding("DATA", "DQ-04", "Forecasts dated before their crop's planting "
            "date", forecast_before or "none",
            "LOW" if forecast_before else "NONE")
    future = sql_one("SELECT COUNT(*) n FROM Harvest WHERE harvest_date > "
                     "CURDATE()")["n"]
    finding("DATA", "DQ-05", "Harvests dated in the future", future,
            "MEDIUM" if future else "NONE")
    dup_harvest = [jsonable(r) for r in sql(
        "SELECT crop_id, harvest_date, COUNT(*) n FROM Harvest GROUP BY "
        "crop_id, harvest_date HAVING COUNT(*) > 1")]
    finding("DATA", "DQ-06", "More than one harvest for the same crop and "
            "day (would duplicate rows of vw_forecast_status)",
            dup_harvest or "none", "HIGH" if dup_harvest else "NONE")
    dup_variety = [jsonable(r) for r in sql(
        "SELECT LOWER(TRIM(name)) name, COUNT(*) n, GROUP_CONCAT(variety_id) "
        "ids, GROUP_CONCAT(DISTINCT color) colors FROM RoseVariety GROUP BY "
        "LOWER(TRIM(name)) HAVING COUNT(*) > 1")]
    finding("DATA", "DQ-07", "Rose varieties sharing a name (pre-existing; "
            "new ones are refused by the API since 2026-11-23)",
            dup_variety or "none", "LOW" if dup_variety else "NONE")
    dup_crop = [jsonable(r) for r in sql(
        "SELECT lot_id, variety_id, planting_date, COUNT(*) n, "
        "GROUP_CONCAT(crop_id) ids FROM Crop GROUP BY lot_id, variety_id, "
        "planting_date HAVING COUNT(*) > 1")]
    finding("DATA", "DQ-08", "Identical crops (same lot, variety and "
            "planting date; pre-existing, new ones refused by the API)",
            dup_crop or "none",
            "LOW" if dup_crop else "NONE")
    area = sql_one("SELECT COUNT(*) n FROM Lot WHERE area <= 0")["n"]
    finding("DATA", "DQ-09", "Lots with area <= 0 (no CHECK in the schema; "
            "enforced by the API only)", area, "LOW" if area else "NONE")


# ----------------------------------------------------------------------
# 3. NFR-01 performance
# ----------------------------------------------------------------------

PERF_QUERIES = {
    "Q1 harvest history: crop + date range": (
        "SELECT * FROM Harvest WHERE crop_id = 1 AND harvest_date BETWEEN "
        "'2026-02-01' AND '2026-02-28'"),
    "Q2 harvest history: date range only": (
        "SELECT * FROM Harvest WHERE harvest_date BETWEEN '2026-02-01' AND "
        "'2026-02-28'"),
    "Q3 production statistics by variety": (
        "SELECT rv.variety_id, rv.name, COUNT(*), SUM(h.quantity), "
        "AVG(h.quantity), MIN(h.quantity), MAX(h.quantity) FROM Harvest h "
        "JOIN Crop c ON c.crop_id = h.crop_id JOIN RoseVariety rv ON "
        "rv.variety_id = c.variety_id GROUP BY rv.variety_id, rv.name"),
    "Q4 production by lot": (
        "SELECT l.lot_id, SUM(h.quantity) FROM Harvest h JOIN Crop c ON "
        "c.crop_id = h.crop_id JOIN Lot l ON l.lot_id = c.lot_id GROUP BY "
        "l.lot_id"),
    "Q5 production by season": (
        "SELECT s.season_id, SUM(h.quantity) FROM Harvest h JOIN Season s ON"
        " s.season_id = h.season_id GROUP BY s.season_id"),
    "Q6 moving-average history (last 3 before a date)": (
        "SELECT quantity FROM Harvest WHERE crop_id = 1 AND harvest_date < "
        "'2026-02-12' ORDER BY harvest_date DESC, harvest_id DESC LIMIT 3"),
    "Q7 forecast status view": "SELECT * FROM vw_forecast_status",
    "Q8 forecast summary view": "SELECT * FROM vw_forecast_summary",
}

API_ENDPOINTS = ["/farms", "/lots", "/varieties", "/crops", "/seasons",
                 "/harvests", "/forecasts", "/forecasts/status",
                 "/forecasts/summary", "/stats/dashboard",
                 "/stats/production?group_by=variety",
                 "/harvests?variety_id=1&date_from=2026-02-01"
                 "&date_to=2026-02-28"]


def timing_stats(samples):
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * len(ordered))) - 1)]
    return {"n": len(samples), "min_ms": round(ordered[0], 3),
            "median_ms": round(statistics.median(ordered), 3),
            "p95_ms": round(p95, 3), "max_ms": round(ordered[-1], 3)}


def section_performance(iterations=30):
    perf = {"row_counts": RESULTS["sections"]["schema"]["row_counts"],
            "sql": {}, "api": {}}
    with engine.connect() as conn:
        for name, query in PERF_QUERIES.items():
            samples = []
            for _ in range(iterations):
                start = time.perf_counter()
                conn.execute(text(query)).all()
                samples.append((time.perf_counter() - start) * 1000)
            plan = [jsonable(r) for r in conn.execute(
                text("EXPLAIN " + query)).mappings()]
            try:
                analyze = conn.execute(text("EXPLAIN ANALYZE " + query)) \
                    .scalar()
            except DBAPIError as exc:
                analyze = f"unavailable: {exc.orig}"
            perf["sql"][name] = {
                "query": query, "timing": timing_stats(samples),
                "explain": [{k: p.get(k) for k in (
                    "table", "type", "possible_keys", "key", "rows",
                    "Extra")} for p in plan],
                "explain_analyze": str(analyze)[:1500],
            }
    for path in API_ENDPOINTS:
        samples, status = [], None
        for _ in range(max(10, iterations // 2)):
            status, _, ms, _, _ = http("GET", path)
            samples.append(ms)
        perf["api"][path] = {"status": status, **timing_stats(samples)}
    samples = []
    body = {"crop_id": 1, "season_id": 1, "forecast_date": "2026-02-12"}
    status = None
    for _ in range(max(10, iterations // 2)):
        status, _, ms, _, _ = http("POST", "/forecasts/generate", body)
        samples.append(ms)
    perf["api"]["POST /forecasts/generate (preview)"] = {
        "status": status, **timing_stats(samples)}
    RESULTS["sections"]["performance"] = perf

    q1 = perf["sql"]["Q1 harvest history: crop + date range"]["explain"][0]
    # Since 2026-11-23 unique_harvest_crop_date has the same columns as
    # idx_harvest_crop_date; MySQL may use either for these range scans.
    crop_date_keys = ("idx_harvest_crop_date", "unique_harvest_crop_date")
    check("NFR-01", "PERF-01", "Crop + date history query uses an index on "
          "(crop_id, harvest_date)", "key in " + "/".join(crop_date_keys),
          f"type={q1['type']} key={q1['key']} rows={q1['rows']}",
          q1["key"] in crop_date_keys)
    q6 = perf["sql"]["Q6 moving-average history (last 3 before a date)"][
        "explain"][0]
    check("NFR-01", "PERF-02", "Forecast history query uses an index on "
          "(crop_id, harvest_date)", "key in " + "/".join(crop_date_keys),
          f"type={q6['type']} key={q6['key']}",
          q6["key"] in crop_date_keys)
    ok = all(v["status"] == 200 for v in perf["api"].values())
    check("NFR-01", "PERF-03", "All measured API read endpoints answer 200",
          200, {k: v["status"] for k, v in perf["api"].items()}, ok)


# ----------------------------------------------------------------------
# 4. NFR-02 constraints (always rolled back)
# ----------------------------------------------------------------------

def section_constraints():
    cases = []
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            def run(sql_text, **params):
                conn.execute(text(sql_text), params)
                return conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()

            farm = run("INSERT INTO Farm (name, location) VALUES "
                       f"('{TAG}_Farm', 'audit')")
            lot = run("INSERT INTO Lot (farm_id, name, area) VALUES "
                      f"(:f, '{TAG}_Lot', 1.00)", f=farm)
            variety = run("INSERT INTO RoseVariety (name, color) VALUES "
                          f"('{TAG}_Variety', 'Red')")
            crop = run("INSERT INTO Crop (lot_id, variety_id, planting_date)"
                       " VALUES (:l, :v, '2000-06-01')", l=lot, v=variety)
            season = run("INSERT INTO Season (name, start_date, end_date) "
                         f"VALUES ('{TAG}_Season', '2001-02-01', "
                         "'2001-02-14')")
            harvest = run("INSERT INTO Harvest (crop_id, season_id, "
                          "harvest_date, quantity) VALUES (:c, :s, "
                          "'2001-02-05', 100)", c=crop, s=season)
            forecast = run("INSERT INTO Forecast (crop_id, season_id, "
                           "forecast_date, estimated_quantity, method) VALUES"
                           " (:c, :s, '2001-02-10', 0, 'audit')",
                           c=crop, s=season)
            cases.append(("NFR-02-01", "Valid rows accepted (incl. "
                          "estimated_quantity = 0)", "accepted",
                          "accepted", True))
            ids = {"farm": farm, "crop": crop, "season": season,
                   "harvest": harvest, "forecast": forecast}

            def expect(case_id, title, statement, codes, **params):
                savepoint = conn.begin_nested()
                try:
                    conn.execute(text(statement), params)
                    actual = "accepted"
                except DBAPIError as exc:
                    actual = exc.orig.args[0]
                savepoint.rollback()
                cases.append((case_id, title, sorted(codes), actual,
                               actual in codes))

            expect("NFR-02-02", "FK: Lot with nonexistent farm",
                   "INSERT INTO Lot (farm_id, name, area) VALUES "
                   "(2147483647, 'x', 1)", {1452})
            expect("NFR-02-03", "FK: Crop with nonexistent variety",
                   "INSERT INTO Crop (lot_id, variety_id, planting_date) "
                   "VALUES (:l, 2147483647, '2000-01-01')", {1452}, l=lot)
            expect("NFR-02-04", "FK: Harvest with nonexistent season",
                   "INSERT INTO Harvest (crop_id, season_id, harvest_date, "
                   "quantity) VALUES (:c, 2147483647, '2001-02-05', 1)",
                   {1452}, c=crop)
            expect("NFR-02-05", "FK: Forecast with nonexistent crop",
                   "INSERT INTO Forecast (crop_id, season_id, forecast_date,"
                   " estimated_quantity, method) VALUES (2147483647, :s, "
                   "'2001-02-05', 1, 'x')", {1452}, s=season)
            expect("NFR-02-06", "FK RESTRICT: delete a farm that has lots",
                   "DELETE FROM Farm WHERE farm_id = :f", {1451}, f=farm)
            expect("NFR-02-07", "FK RESTRICT: delete a crop with harvests",
                   "DELETE FROM Crop WHERE crop_id = :c", {1451}, c=crop)
            expect("NFR-02-08", "FK RESTRICT: update a referenced season id",
                   "UPDATE Season SET season_id = 2147483000 WHERE "
                   "season_id = :s", {1451}, s=season)
            expect("NFR-02-09", "CHECK Harvest_chk_1: quantity = 0",
                   "INSERT INTO Harvest (crop_id, season_id, harvest_date, "
                   "quantity) VALUES (:c, :s, '2001-02-06', 0)", {3819},
                   c=crop, s=season)
            expect("NFR-02-10", "CHECK Harvest_chk_1: quantity < 0",
                   "INSERT INTO Harvest (crop_id, season_id, harvest_date, "
                   "quantity) VALUES (:c, :s, '2001-02-06', -3)", {3819},
                   c=crop, s=season)
            expect("NFR-02-11", "CHECK Season_chk_1: end before start",
                   "INSERT INTO Season (name, start_date, end_date) VALUES "
                   "('x', '2001-05-10', '2001-05-01')", {3819})
            expect("NFR-02-12", "CHECK Forecast_chk_1: negative estimate",
                   "INSERT INTO Forecast (crop_id, season_id, forecast_date,"
                   " estimated_quantity, method) VALUES (:c, :s, "
                   "'2001-02-11', -0.01, 'x')", {3819}, c=crop, s=season)
            expect("NFR-02-13", "UNIQUE unique_crop_forecast_date",
                   "INSERT INTO Forecast (crop_id, season_id, forecast_date,"
                   " estimated_quantity, method) VALUES (:c, :s, "
                   "'2001-02-10', 5, 'x')", {1062}, c=crop, s=season)
            expect("NFR-02-14", "Trigger validate_harvest_season (INSERT)",
                   "INSERT INTO Harvest (crop_id, season_id, harvest_date, "
                   "quantity) VALUES (:c, :s, '2001-03-01', 5)", {1644},
                   c=crop, s=season)
            expect("NFR-02-15", "Trigger validate_harvest_season_update",
                   "UPDATE Harvest SET harvest_date = '2001-04-01' WHERE "
                   "harvest_id = :h", {1644}, h=harvest)
            expect("NFR-02-16", "Trigger validate_forecast_season (INSERT)",
                   "INSERT INTO Forecast (crop_id, season_id, forecast_date,"
                   " estimated_quantity, method) VALUES (:c, :s, "
                   "'2001-06-01', 5, 'x')", {1644}, c=crop, s=season)
            expect("NFR-02-17", "Trigger validate_forecast_season_update",
                   "UPDATE Forecast SET forecast_date = '2001-07-01' WHERE "
                   "forecast_id = :f", {1644}, f=forecast)
            expect("NFR-02-18", "NOT NULL: RoseVariety.name",
                   "INSERT INTO RoseVariety (name, color) VALUES "
                   "(NULL, 'Red')", {1048})
            expect("NFR-02-19", "Type/range: quantity above INT range",
                   "INSERT INTO Harvest (crop_id, season_id, harvest_date, "
                   "quantity) VALUES (:c, :s, '2001-02-07', 9999999999)",
                   {1264}, c=crop, s=season)
            # A second harvest for the same crop and day must be refused by
            # the database (unique_harvest_crop_date, added 2026-11-23);
            # before that it duplicated rows of vw_forecast_status.
            savepoint = conn.begin_nested()
            before = conn.execute(text(
                "SELECT COUNT(*) FROM vw_forecast_status WHERE forecast_id"
                " = :f"), {"f": forecast}).scalar()
            conn.execute(text("INSERT INTO Harvest (crop_id, season_id, "
                              "harvest_date, quantity) VALUES (:c, :s, "
                              "'2001-02-10', 10)"), {"c": crop,
                                                     "s": season})
            code = None
            try:
                inner = conn.begin_nested()
                conn.execute(text("INSERT INTO Harvest (crop_id, season_id, "
                                  "harvest_date, quantity) VALUES (:c, :s, "
                                  "'2001-02-10', 20)"), {"c": crop,
                                                         "s": season})
                inner.rollback()
            except DBAPIError as exc:
                inner.rollback()
                code = exc.orig.args[0]
            after = conn.execute(text(
                "SELECT COUNT(*) FROM vw_forecast_status WHERE forecast_id"
                " = :f"), {"f": forecast}).scalar()
            savepoint.rollback()
            check("NFR-02", "NFR-02-20", "UNIQUE unique_harvest_crop_date: "
                  "a second harvest for the same crop and day is refused, "
                  "so vw_forecast_status keeps one row per forecast",
                  "1062, rows 1", f"{code}, rows {before} -> {after}",
                  code == 1062 and after == 1)
            del ids
        finally:
            trans.rollback()
    leftover = sql_one(f"SELECT COUNT(*) n FROM Farm WHERE name LIKE "
                       f"'{TAG}%'")["n"]
    for case_id, title, expected, actual, passed in cases:
        check("NFR-02", case_id, title, expected, actual, passed)
    check("NFR-02", "NFR-02-21", "Constraint tests left no rows (rolled "
          "back)", 0, leftover, leftover == 0)


# ----------------------------------------------------------------------
# 5. NFR-06 access control and security probes
# ----------------------------------------------------------------------

def counts():
    return {t: sql_one(f"SELECT COUNT(*) n FROM `{t}`")["n"]
            for t in TABLES}


def section_security():
    resources = {"/farms": 1, "/lots": 1, "/varieties": 1, "/crops": 1,
                 "/seasons": 1, "/harvests": 1, "/forecasts": 1}
    before = counts()
    results = []
    for path, sample_id in resources.items():
        for method, suffix, body in (
                ("GET", "", None), ("GET", f"/{sample_id}", None),
                ("POST", "", {"name": "x"}), ("PUT", f"/{sample_id}",
                                              {"name": "x"}),
                ("DELETE", f"/{sample_id}", None)):
            for label, key in (("no key", None), ("wrong key", "wrong-key"),
                               ("empty key", "")):
                status, body_json, _, _, _ = http(method, path + suffix,
                                                  body, key=key)
                results.append((f"{method} {path}{suffix}", label, status))
    after = counts()
    denied = [r for r in results if r[2] == 401]
    check("NFR-06", "SEC-01", "Every protected operation (7 resources x 5 "
          "operations x 3 bad credentials) is refused with 401",
          f"{len(results)} x 401", f"{len(denied)} x 401",
          len(denied) == len(results),
          detail=[f"{r[0]} [{r[1]}] -> {r[2]}" for r in results
                  if r[2] != 401])
    check("NFR-06", "SEC-02", "Refused requests did not change the database",
          before, after, before == after)
    ok = all(http("GET", p)[0] == 200 for p in resources)
    check("NFR-06", "SEC-03", "Valid key reads all 7 resources", 200,
          "all 200" if ok else "some failed", ok)

    # GUI session path with cookie + CSRF header
    cookie_jar = http_cookiejar()
    session_opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(cookie_jar))
    status, body, _, hdrs, _ = http(
        "POST", "/auth/login", {"api_key": "wrong"}, key=None,
        opener=session_opener)
    check("NFR-06", "SEC-04", "GUI login with a wrong key", 401, status,
          status == 401)
    status, body, _, hdrs, _ = http(
        "POST", "/auth/login", {"api_key": KEY}, key=None,
        opener=session_opener)
    cookie = hdrs.get("Set-Cookie", "")
    check("NFR-06", "SEC-05", "GUI login sets an HttpOnly SameSite=Strict "
          "cookie that does not contain the key",
          "200 + HttpOnly + SameSite=Strict",
          f"{status} HttpOnly={'HttpOnly' in cookie} "
          f"Strict={'SameSite=Strict' in cookie} "
          f"key_in_cookie={bool(KEY) and KEY in cookie}",
          status == 200 and "HttpOnly" in cookie
          and "SameSite=Strict" in cookie and KEY not in cookie)
    status, _, _, _, _ = http("POST", "/varieties",
                              {"name": f"{TAG}_csrf", "color": "Red"},
                              key=None, opener=session_opener)
    check("NFR-06", "SEC-06", "Session write without the GUI header is "
          "refused (CSRF protection)", 403, status, status == 403)
    status, body, _, _, _ = http(
        "POST", "/varieties", {"name": f"{TAG}_session", "color": "Red"},
        key=None, opener=session_opener,
        headers={"X-Requested-With": "RoseProductionGUI"})
    if status == 201:
        CREATED["RoseVariety"].append(body["variety"]["variety_id"])
    check("NFR-06", "SEC-07", "Session write with the GUI header is "
          "accepted", 201, status, status == 201)
    http("POST", "/auth/logout", key=None, opener=session_opener,
         headers={"X-Requested-With": "RoseProductionGUI"})
    status, _, _, _, _ = http("GET", "/farms", key=None,
                              opener=session_opener)
    check("NFR-06", "SEC-08", "After logout the session no longer works",
          401, status, status == 401)

    # CORS
    status, _, _, hdrs, _ = http("GET", "/farms",
                                 headers={"Origin": "http://evil.example"})
    pre, _, _, pre_hdrs, _ = http(
        "OPTIONS", "/farms", key=None,
        headers={"Origin": "http://evil.example",
                 "Access-Control-Request-Method": "DELETE",
                 "Access-Control-Request-Headers": "X-API-Key"})
    acao = hdrs.get("Access-Control-Allow-Origin") or pre_hdrs.get(
        "Access-Control-Allow-Origin")
    check("NFR-06", "SEC-09", "No CORS: cross-origin requests get no "
          "Access-Control-Allow-Origin", None, acao, acao is None)

    # Injection probes
    probes = [("GET", "/harvests?crop_id=1%20OR%201%3D1", 400),
              ("GET", "/harvests?date_from=2026-01-01'%20OR%20'1'='1", 400),
              ("GET", "/stats/production?group_by=variety;DROP%20TABLE%20"
                      "Farm", 400),
              ("GET", "/farms/1%20OR%201=1", 404)]
    for index, (method, path, expected) in enumerate(probes, 1):
        status, _, _, _, _ = http(method, path)
        check("NFR-06", f"SEC-10.{index}", f"Injection probe {path}",
              expected, status, status == expected)
    payload = f"{TAG}_x'); DROP TABLE Farm; --"
    status, body, _, _, _ = http("POST", "/varieties",
                                 {"name": payload, "color": "Red"})
    stored = None
    if status == 201:
        vid = body["variety"]["variety_id"]
        CREATED["RoseVariety"].append(vid)
        stored = sql_one("SELECT name FROM RoseVariety WHERE variety_id = "
                         ":v", v=vid)["name"]
    farm_table = sql_one("SELECT COUNT(*) n FROM information_schema.TABLES "
                         "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = "
                         "'Farm'")["n"]
    check("NFR-06", "SEC-11", "SQL text in a field is stored literally "
          "(parameterised queries)", "stored literally, Farm still exists",
          f"stored_equal={stored == payload} farm_table={farm_table}",
          stored == payload and farm_table == 1)

    # Error hygiene
    status, body, _, _, raw = http("POST", "/harvests", raw=b"{bad json")
    leaked = any(marker in raw.decode(errors="ignore") for marker in (
        "Traceback", "File \"", "sqlalchemy", "pymysql"))
    check("NFR-06", "SEC-12", "Malformed JSON gives a JSON 400 without "
          "stack trace or driver details", "400, no trace",
          f"{status}, leaked={leaked}", status == 400 and not leaked)
    status, _, _, _, _ = http("POST", "/varieties",
                              raw=b'{"name":"' + b"x" * (1024 * 1024 + 50)
                              + b'","color":"Red"}')
    check("NFR-06", "SEC-13", "Request body above 1 MiB rejected", 413,
          status, status == 413)

    # Key exposure in the GUI assets
    status, _, _, _, html = http("GET", "/app/", key=None)
    assets = re.findall(rb'(?:src|href)="(/app/[^"]+)"', html or b"")
    exposed = []
    for asset in [b"/app/"] + assets:
        _, _, _, _, content = http("GET", asset.decode(), key=None)
        if KEY and KEY.encode() in (content or b""):
            exposed.append(asset.decode())
    check("NFR-06", "SEC-14", "API key absent from the served GUI (HTML + "
          "JS + CSS bundles)", [], exposed, status == 200 and not exposed,
          assets=[a.decode() for a in assets])
    status, _, _, _, content = http("GET", "/app/..%2F.env", key=None)
    check("NFR-06", "SEC-15", "Path traversal does not serve .env",
          "no secrets", f"{status}", not (KEY and KEY.encode() in content))
    status, _, _, hdrs, _ = http("GET", "/farms")
    check("NFR-06", "SEC-16", "Security headers on API responses",
          "nosniff, DENY, CSP, no-store",
          {k: hdrs.get(k) for k in ("X-Content-Type-Options",
                                    "X-Frame-Options", "Cache-Control")},
          hdrs.get("X-Content-Type-Options") == "nosniff"
          and hdrs.get("X-Frame-Options") == "DENY"
          and "default-src" in (hdrs.get("Content-Security-Policy") or "")
          and hdrs.get("Cache-Control") == "no-store")


def http_cookiejar():
    import http.cookiejar as cj
    return cj.CookieJar()


# ----------------------------------------------------------------------
# 6. CRUD matrix
# ----------------------------------------------------------------------

CRUD = []


def crud_step(entity, operation, method, path, body, expected, db_query=None,
              db_expect=None, created_table=None, id_key=None, **params):
    status, response, ms, _, _ = http(method, path, body)
    new_id = None
    if created_table and status == 201 and response:
        item = next(v for k, v in response.items() if isinstance(v, dict))
        new_id = item[id_key]
        CREATED[created_table].append(new_id)
    db_effect, db_ok = None, True
    if db_query:
        values = dict(params)
        if new_id is not None:
            values["id"] = new_id
        row = sql_one(db_query, **values)
        db_effect = jsonable(row) if row else None
        db_ok = db_expect(db_effect) if db_expect else True
    passed = status == expected and db_ok
    entry = {"entity": entity, "operation": operation, "method": method,
             "endpoint": path, "input": body, "expected_status": expected,
             "actual_status": status, "db_effect": db_effect,
             "ms": round(ms, 1), "result": "PASS" if passed else "FAIL"}
    CRUD.append(redact(entry))
    check("CRUD", f"{entity}:{operation}", f"{method} {path}", expected,
          status, passed, db_effect=db_effect)
    return response, new_id


def section_crud():
    fresh = {}
    # ---------- Farm
    _, farm_id = crud_step(
        "Farm", "POST", "POST", "/farms",
        {"name": f"{TAG}_Farm", "location": "Audit location"}, 201,
        "SELECT * FROM Farm WHERE farm_id = :id",
        lambda r: r and r["name"] == f"{TAG}_Farm", "Farm", "farm_id")
    crud_step("Farm", "GET all", "GET", "/farms", None, 200)
    crud_step("Farm", "GET by id", "GET", f"/farms/{farm_id}", None, 200)
    crud_step("Farm", "PUT", "PUT", f"/farms/{farm_id}",
              {"name": f"{TAG}_Farm2", "location": "Updated"}, 200,
              "SELECT * FROM Farm WHERE farm_id = :fid",
              lambda r: r["name"] == f"{TAG}_Farm2"
              and r["location"] == "Updated", fid=farm_id)
    fresh["farm"] = farm_id
    # ---------- Lot
    _, lot_id = crud_step(
        "Lot", "POST", "POST", "/lots",
        {"farm_id": farm_id, "name": f"{TAG}_Lot", "area": 2.5}, 201,
        "SELECT * FROM Lot WHERE lot_id = :id",
        lambda r: r and r["farm_id"] == farm_id and r["area"] == 2.5,
        "Lot", "lot_id")
    crud_step("Lot", "GET all", "GET", "/lots", None, 200)
    crud_step("Lot", "GET by id", "GET", f"/lots/{lot_id}", None, 200)
    crud_step("Lot", "PUT", "PUT", f"/lots/{lot_id}",
              {"farm_id": farm_id, "name": f"{TAG}_Lot2", "area": 3.75}, 200,
              "SELECT * FROM Lot WHERE lot_id = :lid",
              lambda r: r["name"] == f"{TAG}_Lot2" and r["area"] == 3.75,
              lid=lot_id)
    # ---------- RoseVariety
    _, variety_id = crud_step(
        "RoseVariety", "POST", "POST", "/varieties",
        {"name": f"{TAG}_Variety", "color": "Purple"}, 201,
        "SELECT * FROM RoseVariety WHERE variety_id = :id",
        lambda r: r and r["color"] == "Purple", "RoseVariety", "variety_id")
    crud_step("RoseVariety", "GET all", "GET", "/varieties", None, 200)
    crud_step("RoseVariety", "GET by id", "GET", f"/varieties/{variety_id}",
              None, 200)
    crud_step("RoseVariety", "PUT", "PUT", f"/varieties/{variety_id}",
              {"name": f"{TAG}_Variety2", "color": "Red"}, 200,
              "SELECT * FROM RoseVariety WHERE variety_id = :vid",
              lambda r: r["name"] == f"{TAG}_Variety2"
              and r["color"] == "Red", vid=variety_id)
    # ---------- Crop
    _, crop_id = crud_step(
        "Crop", "POST", "POST", "/crops",
        {"lot_id": lot_id, "variety_id": variety_id,
         "planting_date": f"{PAST_YEAR - 1}-06-01"}, 201,
        "SELECT * FROM Crop WHERE crop_id = :id",
        lambda r: r and r["lot_id"] == lot_id
        and r["variety_id"] == variety_id, "Crop", "crop_id")
    crud_step("Crop", "GET all", "GET", "/crops", None, 200)
    crud_step("Crop", "GET by id", "GET", f"/crops/{crop_id}", None, 200)
    crud_step("Crop", "PUT", "PUT", f"/crops/{crop_id}",
              {"lot_id": lot_id, "variety_id": variety_id,
               "planting_date": f"{PAST_YEAR - 1}-05-01"}, 200,
              "SELECT planting_date FROM Crop WHERE crop_id = :cid",
              lambda r: r["planting_date"] == f"{PAST_YEAR - 1}-05-01",
              cid=crop_id)
    # ---------- Season
    _, season_id = crud_step(
        "Season", "POST", "POST", "/seasons",
        {"name": f"{TAG}_Season", "start_date": f"{PAST_YEAR}-02-01",
         "end_date": f"{PAST_YEAR}-02-14"}, 201,
        "SELECT * FROM Season WHERE season_id = :id",
        lambda r: r and r["end_date"] == f"{PAST_YEAR}-02-14",
        "Season", "season_id")
    crud_step("Season", "GET all", "GET", "/seasons", None, 200)
    crud_step("Season", "GET by id", "GET", f"/seasons/{season_id}", None,
              200)
    crud_step("Season", "PUT", "PUT", f"/seasons/{season_id}",
              {"name": f"{TAG}_Season2", "start_date": f"{PAST_YEAR}-02-01",
               "end_date": f"{PAST_YEAR}-02-28"}, 200,
              "SELECT * FROM Season WHERE season_id = :sid",
              lambda r: r["end_date"] == f"{PAST_YEAR}-02-28",
              sid=season_id)
    # ---------- Harvest
    _, harvest_id = crud_step(
        "Harvest", "POST", "POST", "/harvests",
        {"crop_id": crop_id, "season_id": season_id,
         "harvest_date": f"{PAST_YEAR}-02-05", "quantity": 1234}, 201,
        "SELECT * FROM Harvest WHERE harvest_id = :id",
        lambda r: r and r["quantity"] == 1234, "Harvest", "harvest_id")
    crud_step("Harvest", "GET all", "GET", "/harvests", None, 200)
    crud_step("Harvest", "GET by id", "GET", f"/harvests/{harvest_id}",
              None, 200)
    crud_step("Harvest", "PUT", "PUT", f"/harvests/{harvest_id}",
              {"crop_id": crop_id, "season_id": season_id,
               "harvest_date": f"{PAST_YEAR}-02-06", "quantity": 1300}, 200,
              "SELECT * FROM Harvest WHERE harvest_id = :hid",
              lambda r: r["quantity"] == 1300
              and r["harvest_date"] == f"{PAST_YEAR}-02-06", hid=harvest_id)
    # ---------- Forecast
    _, forecast_id = crud_step(
        "Forecast", "POST", "POST", "/forecasts",
        {"crop_id": crop_id, "season_id": season_id,
         "forecast_date": f"{PAST_YEAR}-02-20", "estimated_quantity": 1500.5,
         "method": "Audit manual"}, 201,
        "SELECT * FROM Forecast WHERE forecast_id = :id",
        lambda r: r and r["estimated_quantity"] == 1500.5,
        "Forecast", "forecast_id")
    crud_step("Forecast", "GET all", "GET", "/forecasts", None, 200)
    crud_step("Forecast", "GET by id", "GET", f"/forecasts/{forecast_id}",
              None, 200)
    crud_step("Forecast", "PUT", "PUT", f"/forecasts/{forecast_id}",
              {"crop_id": crop_id, "season_id": season_id,
               "forecast_date": f"{PAST_YEAR}-02-21",
               "estimated_quantity": 0, "method": "Audit manual v2"}, 200,
              "SELECT * FROM Forecast WHERE forecast_id = :fid",
              lambda r: r["estimated_quantity"] == 0
              and r["forecast_date"] == f"{PAST_YEAR}-02-21",
              fid=forecast_id)

    # ---------- negative / conflict cases
    neg = [
        ("Farm", "POST missing fields", "POST", "/farms", {}, 400),
        ("Farm", "POST invalid type", "POST", "/farms",
         {"name": 5, "location": "x"}, 400),
        ("Farm", "GET missing id", "GET", "/farms/999999999", None, 404),
        ("Farm", "PUT missing id", "PUT", "/farms/999999999",
         {"name": "x", "location": "y"}, 404),
        ("Farm", "DELETE in use (has lot)", "DELETE", f"/farms/{farm_id}",
         None, 409),
        ("Lot", "POST invalid FK farm", "POST", "/lots",
         {"farm_id": 999999999, "name": "x", "area": 1}, 400),
        ("Lot", "POST area <= 0", "POST", "/lots",
         {"farm_id": farm_id, "name": "x", "area": 0}, 400),
        ("Lot", "DELETE missing id", "DELETE", "/lots/999999999", None, 404),
        ("Lot", "DELETE in use (has crop)", "DELETE", f"/lots/{lot_id}",
         None, 409),
        ("RoseVariety", "POST too long", "POST", "/varieties",
         {"name": "x" * 101, "color": "Red"}, 400),
        ("RoseVariety", "DELETE in use (has crop)", "DELETE",
         f"/varieties/{variety_id}", None, 409),
        ("Crop", "POST invalid FK variety", "POST", "/crops",
         {"lot_id": lot_id, "variety_id": 999999999,
          "planting_date": "2000-01-01"}, 400),
        ("Crop", "POST invalid date", "POST", "/crops",
         {"lot_id": lot_id, "variety_id": variety_id,
          "planting_date": "2001-02-30"}, 400),
        ("Crop", "DELETE in use (has harvest)", "DELETE", f"/crops/{crop_id}",
         None, 409),
        ("Season", "POST end before start", "POST", "/seasons",
         {"name": "x", "start_date": "2001-05-10",
          "end_date": "2001-05-01"}, 400),
        ("Season", "DELETE in use (has harvest)", "DELETE",
         f"/seasons/{season_id}", None, 409),
        ("Harvest", "POST quantity 0", "POST", "/harvests",
         {"crop_id": crop_id, "season_id": season_id,
          "harvest_date": f"{PAST_YEAR}-02-07", "quantity": 0}, 400),
        ("Harvest", "POST quantity not integer", "POST", "/harvests",
         {"crop_id": crop_id, "season_id": season_id,
          "harvest_date": f"{PAST_YEAR}-02-07", "quantity": 1.5}, 400),
        ("Harvest", "POST outside season", "POST", "/harvests",
         {"crop_id": crop_id, "season_id": season_id,
          "harvest_date": f"{PAST_YEAR}-03-15", "quantity": 5}, 400),
        ("Harvest", "POST invalid FK crop", "POST", "/harvests",
         {"crop_id": 999999999, "season_id": season_id,
          "harvest_date": f"{PAST_YEAR}-02-07", "quantity": 5}, 400),
        ("Harvest", "POST duplicate crop+day", "POST", "/harvests",
         {"crop_id": crop_id, "season_id": season_id,
          "harvest_date": f"{PAST_YEAR}-02-06", "quantity": 5}, 409),
        ("Harvest", "POST before planting", "POST", "/harvests",
         {"crop_id": crop_id, "season_id": season_id,
          "harvest_date": f"{PAST_YEAR}-02-07", "quantity": 5}, None),
        ("Forecast", "POST negative estimate", "POST", "/forecasts",
         {"crop_id": crop_id, "season_id": season_id,
          "forecast_date": f"{PAST_YEAR}-02-22", "estimated_quantity": -1,
          "method": "x"}, 400),
        ("Forecast", "POST duplicate crop+date", "POST", "/forecasts",
         {"crop_id": crop_id, "season_id": season_id,
          "forecast_date": f"{PAST_YEAR}-02-21", "estimated_quantity": 1,
          "method": "x"}, 409),
        ("Forecast", "POST invalid FK season", "POST", "/forecasts",
         {"crop_id": crop_id, "season_id": 999999999,
          "forecast_date": f"{PAST_YEAR}-02-22", "estimated_quantity": 1,
          "method": "x"}, 400),
        ("Forecast", "PUT missing id", "PUT", "/forecasts/999999999", {},
         404),
        ("Harvest", "POST invalid JSON", "POST", "/harvests", None, 400),
    ]
    before = counts()
    for entity, operation, method, path, body, expected in neg:
        if operation == "POST before planting":
            continue  # covered in the FR-03 section with its own crop
        if operation == "POST invalid JSON":
            status, _, ms, _, _ = http(method, path, raw=b"{oops")
        else:
            status, _, ms, _, _ = http(method, path, body)
        passed = status == expected
        CRUD.append(redact({"entity": entity, "operation": operation,
                            "method": method, "endpoint": path,
                            "input": body, "expected_status": expected,
                            "actual_status": status,
                            "db_effect": "no change expected",
                            "ms": round(ms, 1),
                            "result": "PASS" if passed else "FAIL"}))
        check("CRUD", f"{entity}:{operation}", f"{method} {path}", expected,
              status, passed)
    after = counts()
    check("CRUD", "NEG-DB", "Rejected requests did not change any table",
          before, after, before == after)

    # ---------- deletes (children first) + 404 afterwards
    for entity, path, table, key, value in (
            ("Forecast", f"/forecasts/{forecast_id}", "Forecast",
             "forecast_id", forecast_id),
            ("Harvest", f"/harvests/{harvest_id}", "Harvest", "harvest_id",
             harvest_id),
            ("Crop", f"/crops/{crop_id}", "Crop", "crop_id", crop_id),
            ("Season", f"/seasons/{season_id}", "Season", "season_id",
             season_id),
            ("Lot", f"/lots/{lot_id}", "Lot", "lot_id", lot_id),
            ("RoseVariety", f"/varieties/{variety_id}", "RoseVariety",
             "variety_id", variety_id),
            ("Farm", f"/farms/{farm_id}", "Farm", "farm_id", farm_id)):
        crud_step(entity, "DELETE", "DELETE", path, None, 200,
                  f"SELECT COUNT(*) AS n FROM `{table}` WHERE `{key}` = :v",
                  lambda r: r["n"] == 0, v=value)
        crud_step(entity, "GET after DELETE", "GET", path, None, 404)
    RESULTS["sections"]["crud_matrix"] = CRUD
    # Read-only GET by id of real records, compared with SQL.
    real = []
    for path, table, key in (("/farms", "Farm", "farm_id"),
                             ("/lots", "Lot", "lot_id"),
                             ("/varieties", "RoseVariety", "variety_id"),
                             ("/crops", "Crop", "crop_id"),
                             ("/seasons", "Season", "season_id"),
                             ("/harvests", "Harvest", "harvest_id"),
                             ("/forecasts", "Forecast", "forecast_id")):
        row = sql_one(f"SELECT `{key}` AS id FROM `{table}` ORDER BY `{key}`"
                      " LIMIT 1")
        if not row:
            continue
        status, body, _, _, _ = http("GET", f"{path}/{row['id']}")
        item = next(v for v in (body or {}).values() if isinstance(v, dict))
        real.append((path, row["id"], status, item.get(key) == row["id"]))
    check("CRUD", "REAL-GET", "GET by id of the first real record of each "
          "table returns it", "7 x 200", real,
          all(r[2] == 200 and r[3] for r in real) and len(real) == 7)


# ----------------------------------------------------------------------
# 7. Functional requirements with isolated data
# ----------------------------------------------------------------------

def make(path, body, table, key):
    status, response, _, _, _ = http("POST", path, body)
    if status != 201:
        raise RuntimeError(f"setup {path} failed: {status} {response}")
    item = next(v for v in response.values() if isinstance(v, dict))
    CREATED[table].append(item[key])
    return item


def section_functional():
    farm = make("/farms", {"name": f"{TAG}_FR_Farm", "location": "audit"},
                "Farm", "farm_id")
    lot_a = make("/lots", {"farm_id": farm["farm_id"],
                           "name": f"{TAG}_LotA", "area": 1.5}, "Lot",
                 "lot_id")
    lot_b = make("/lots", {"farm_id": farm["farm_id"],
                           "name": f"{TAG}_LotB", "area": 2.0}, "Lot",
                 "lot_id")
    var_a = make("/varieties", {"name": f"{TAG}_VarA", "color": "Red"},
                 "RoseVariety", "variety_id")
    var_b = make("/varieties", {"name": f"{TAG}_VarB", "color": "White"},
                 "RoseVariety", "variety_id")
    crop_a = make("/crops", {"lot_id": lot_a["lot_id"],
                             "variety_id": var_a["variety_id"],
                             "planting_date": f"{PAST_YEAR - 1}-06-01"},
                  "Crop", "crop_id")
    crop_b = make("/crops", {"lot_id": lot_b["lot_id"],
                             "variety_id": var_b["variety_id"],
                             "planting_date": f"{PAST_YEAR}-02-10"},
                  "Crop", "crop_id")
    s1 = make("/seasons", {"name": f"{TAG}_Valentine",
                           "start_date": f"{PAST_YEAR}-02-01",
                           "end_date": f"{PAST_YEAR}-02-14"}, "Season",
              "season_id")
    s2 = make("/seasons", {"name": f"{TAG}_Mothers",
                           "start_date": f"{PAST_YEAR}-05-01",
                           "end_date": f"{PAST_YEAR}-05-10"}, "Season",
              "season_id")
    future = make("/seasons", {"name": f"{TAG}_Future",
                               "start_date": f"{FUTURE_YEAR}-02-01",
                               "end_date": f"{FUTURE_YEAR}-02-14"},
                  "Season", "season_id")

    # FR-03: register harvests (date, lot, variety, quantity)
    plan = [(crop_a, s1, f"{PAST_YEAR}-02-02", 1000),
            (crop_a, s1, f"{PAST_YEAR}-02-04", 1300),
            (crop_a, s1, f"{PAST_YEAR}-02-06", 1600),
            (crop_a, s2, f"{PAST_YEAR}-05-03", 1250),
            (crop_b, s1, f"{PAST_YEAR}-02-12", 800),
            (crop_b, s2, f"{PAST_YEAR}-05-04", 900)]
    harvests = []
    for crop, season, day, qty in plan:
        harvests.append(make("/harvests", {
            "crop_id": crop["crop_id"], "season_id": season["season_id"],
            "harvest_date": day, "quantity": qty}, "Harvest", "harvest_id"))
    joined = sql_one(
        "SELECT h.harvest_date, h.quantity, l.name AS lot, rv.name AS "
        "variety, s.name AS season FROM Harvest h JOIN Crop c USING "
        "(crop_id) JOIN Lot l ON l.lot_id = c.lot_id JOIN RoseVariety rv ON"
        " rv.variety_id = c.variety_id JOIN Season s ON s.season_id = "
        "h.season_id WHERE h.harvest_id = :h", h=harvests[0]["harvest_id"])
    api_item = http("GET", f"/harvests/{harvests[0]['harvest_id']}")[1][
        "harvest"]
    check("FR-03", "FR-03-01", "Harvest registered with date, lot, variety "
          "and quantity; SQL join and API agree",
          {"date": f"{PAST_YEAR}-02-02", "lot": lot_a["name"],
           "variety": var_a["name"], "quantity": 1000},
          {"sql": jsonable(joined), "api": {
              "date": api_item["harvest_date"], "lot": api_item["crop"]["lot"],
              "variety": api_item["crop"]["variety"],
              "quantity": api_item["quantity"]}},
          joined["lot"] == lot_a["name"] and joined["variety"] == var_a[
              "name"] and joined["quantity"] == 1000
          and api_item["crop"]["lot"] == lot_a["name"]
          and api_item["crop"]["variety"] == var_a["name"])
    status = http("POST", "/harvests", {
        "crop_id": crop_b["crop_id"], "season_id": s1["season_id"],
        "harvest_date": f"{PAST_YEAR}-02-05", "quantity": 5})
    check("FR-03", "FR-03-02", "Harvest before the crop's planting date "
          "rejected", "400 DATE_BEFORE_PLANTING",
          f"{status[0]} {(status[1] or {}).get('code')}",
          status[0] == 400
          and (status[1] or {}).get("code") == "DATE_BEFORE_PLANTING")
    tomorrow = TODAY + dt.timedelta(days=1)
    current = make("/seasons", {
        "name": f"{TAG}_Current",
        "start_date": (TODAY - dt.timedelta(days=3)).isoformat(),
        "end_date": (TODAY + dt.timedelta(days=10)).isoformat()},
        "Season", "season_id")
    status = http("POST", "/harvests", {
        "crop_id": crop_a["crop_id"], "season_id": current["season_id"],
        "harvest_date": tomorrow.isoformat(), "quantity": 5})
    check("FR-03", "FR-03-03", "Harvest dated in the future (inside a "
          "valid season) rejected", "400 FUTURE_HARVEST_DATE",
          f"{status[0]} {(status[1] or {}).get('code')}",
          status[0] == 400
          and (status[1] or {}).get("code") == "FUTURE_HARVEST_DATE")
    status = http("POST", "/harvests", {
        "crop_id": crop_a["crop_id"], "season_id": s1["season_id"],
        "harvest_date": f"{PAST_YEAR}-02-02", "quantity": 5})
    check("FR-03", "FR-03-04", "Second harvest for the same crop and day "
          "rejected", "409 DUPLICATE_RECORD",
          f"{status[0]} {(status[1] or {}).get('code')}", status[0] == 409)

    ids = {h["harvest_id"] for h in harvests}

    def api_ids(query):
        body = http("GET", "/harvests?" + query)[1]
        return {h["harvest_id"] for h in body["harvests"]} & ids

    def expected_ids(pred):
        return {h["harvest_id"] for h, p in zip(harvests, plan) if pred(p)}

    cases = [
        ("FR-05-01", "by date range",
         f"date_from={PAST_YEAR}-02-03&date_to={PAST_YEAR}-02-12",
         lambda p: f"{PAST_YEAR}-02-03" <= p[2] <= f"{PAST_YEAR}-02-12"),
        ("FR-05-02", "by single date",
         f"date_from={PAST_YEAR}-02-04&date_to={PAST_YEAR}-02-04",
         lambda p: p[2] == f"{PAST_YEAR}-02-04"),
        ("FR-05-03", "by rose variety", f"variety_id={var_b['variety_id']}",
         lambda p: p[0] is crop_b),
        ("FR-05-04", "by cultivation lot", f"lot_id={lot_a['lot_id']}",
         lambda p: p[0] is crop_a),
        ("FR-05-05", "by season", f"season_id={s2['season_id']}",
         lambda p: p[1] is s2),
        ("FR-05-06", "combined: variety + season",
         f"variety_id={var_a['variety_id']}&season_id={s1['season_id']}",
         lambda p: p[0] is crop_a and p[1] is s1),
    ]
    for case_id, title, query, pred in cases:
        got, want = api_ids(query), expected_ids(pred)
        check("FR-05", case_id, f"Historical production filtered {title}",
              sorted(want), sorted(got), got == want)
    # Same filters on the whole real data set, compared with SQL counts.
    mismatches = []
    for dimension, sql_col, table, key in (
            ("variety_id", "c.variety_id", "RoseVariety", "variety_id"),
            ("lot_id", "c.lot_id", "Lot", "lot_id"),
            ("season_id", "h.season_id", "Season", "season_id")):
        for row in sql(f"SELECT `{key}` AS id FROM `{table}`"):
            api_count = http("GET", f"/harvests?{dimension}={row['id']}")[1][
                "count"]
            sql_count = sql_one(
                f"SELECT COUNT(*) n FROM Harvest h JOIN Crop c USING "
                f"(crop_id) WHERE {sql_col} = :v", v=row["id"])["n"]
            if api_count != sql_count:
                mismatches.append((dimension, row["id"], api_count,
                                   sql_count))
    check("FR-05", "FR-05-07", "Every variety/lot/season filter on the full "
          "data set matches an independent SQL count", "no mismatch",
          mismatches or "no mismatch", not mismatches)

    # FR-06 statistics on known data
    stats = http("GET", f"/stats/production?group_by=variety&variety_id="
                        f"{var_a['variety_id']}")[1]["overall"]
    qty = [1000, 1300, 1600, 1250]
    want = {"total": sum(qty), "average": round(sum(qty) / len(qty), 2),
            "minimum": min(qty), "maximum": max(qty), "records": len(qty)}
    check("FR-06", "FR-06-01", "Total/average/min/max for known data "
          "(variety A: 1000, 1300, 1600, 1250)", want, stats, stats == want)
    by_lot = http("GET", "/stats/production?group_by=lot&date_from="
                         f"{PAST_YEAR}-01-01&date_to={PAST_YEAR}-12-31")[1]
    lot_b_row = next(g for g in by_lot["groups"]
                     if g["key"] == lot_b["lot_id"])
    check("FR-06", "FR-06-02", "Statistics grouped by lot for a date range",
          {"total": 1700, "average": 850.0, "minimum": 800, "maximum": 900},
          {k: lot_b_row[k] for k in ("total", "average", "minimum",
                                     "maximum")},
          (lot_b_row["total"], lot_b_row["average"], lot_b_row["minimum"],
           lot_b_row["maximum"]) == (1700, 850.0, 800, 900))
    real = http("GET", "/stats/production?group_by=variety")[1]
    sql_rows = {r["vid"]: r for r in sql(
        "SELECT rv.variety_id vid, SUM(h.quantity) total, ROUND(AVG("
        "h.quantity), 2) avg, MIN(h.quantity) mn, MAX(h.quantity) mx, "
        "COUNT(*) n FROM Harvest h JOIN Crop c USING (crop_id) JOIN "
        "RoseVariety rv ON rv.variety_id = c.variety_id GROUP BY "
        "rv.variety_id")}
    diffs = []
    for group in real["groups"]:
        ref = sql_rows.get(group["key"])
        if not ref or (group["total"], group["minimum"], group["maximum"],
                       group["records"]) != (int(ref["total"]), ref["mn"],
                                             ref["mx"], ref["n"]) \
                or abs(group["average"] - float(ref["avg"])) > 0.01:
            diffs.append(group["label"])
    check("FR-06", "FR-06-03", "Statistics of every variety in the full "
          "data set match an independent SQL aggregate", "no difference",
          diffs or "no difference", not diffs and len(real["groups"]) ==
          len(sql_rows))
    dashboard = http("GET", "/stats/dashboard")[1]
    total = sql_one("SELECT COALESCE(SUM(quantity),0) t FROM Harvest")["t"]
    check("FR-06", "FR-06-04", "Dashboard total equals SUM(quantity)",
          int(total), dashboard["production"]["total"],
          dashboard["production"]["total"] == int(total))

    # FR-07 forecasting
    def generate(crop, season, day, save=False, window=None):
        body = {"crop_id": crop["crop_id"], "season_id": season["season_id"],
                "forecast_date": day, "save": save}
        if window:
            body["window"] = window
        return http("POST", "/forecasts/generate", body)

    status, body, ms, _, _ = generate(crop_a, future, f"{FUTURE_YEAR}-02-10")
    expected_est = round((1300 + 1600 + 1250) / 3, 2)
    calc = (body or {}).get("calculation", {})
    check("FR-07", "FR-07-01", "Forecast for a FUTURE date = mean of the 3 "
          "latest earlier harvests of the crop",
          {"status": 200, "estimate": expected_est,
           "history": [1250, 1600, 1300]},
          {"status": status, "estimate": calc.get("estimated_quantity"),
           "history": [h["quantity"] for h in calc.get("history", [])],
           "method": calc.get("method"), "ms": round(ms, 1)},
          status == 200 and calc.get("estimated_quantity") == expected_est
          and [h["quantity"] for h in calc["history"]] == [1250, 1600, 1300])
    check("FR-07", "FR-07-02", "Preview does not write", 0,
          sql_one("SELECT COUNT(*) n FROM Forecast WHERE crop_id = :c",
                  c=crop_a["crop_id"])["n"],
          sql_one("SELECT COUNT(*) n FROM Forecast WHERE crop_id = :c",
                  c=crop_a["crop_id"])["n"] == 0)
    status, body, _, _, _ = generate(crop_a, s1, f"{PAST_YEAR}-02-05")
    check("FR-07", "FR-07-03", "Only harvests before the forecast date are "
          "used (2 available -> refused)", "400 INSUFFICIENT_HISTORY",
          f"{status} {(body or {}).get('code')}",
          status == 400 and (body or {}).get("code") ==
          "INSUFFICIENT_HISTORY")
    status, body, _, _, _ = generate(crop_a, s1, f"{PAST_YEAR}-03-01")
    check("FR-07", "FR-07-04", "Forecast date outside the season refused",
          "400 DATE_OUTSIDE_SEASON", f"{status} {(body or {}).get('code')}",
          status == 400)
    status, body, _, _, _ = generate(crop_a, future, f"{FUTURE_YEAR}-02-10",
                                     window=2)
    check("FR-07", "FR-07-05", "Configurable window N=2",
          round((1600 + 1250) / 2, 2),
          (body or {}).get("calculation", {}).get("estimated_quantity"),
          (body or {}).get("calculation", {}).get("estimated_quantity") ==
          round((1600 + 1250) / 2, 2))
    real_crop = sql_one("SELECT c.crop_id, MAX(h.harvest_date) last FROM "
                        "Crop c JOIN Harvest h USING (crop_id) GROUP BY "
                        "c.crop_id HAVING COUNT(*) >= 3 ORDER BY c.crop_id "
                        "LIMIT 1")
    if real_crop:
        season_row = sql_one(
            "SELECT season_id FROM Season WHERE :d BETWEEN start_date AND "
            "end_date ORDER BY start_date LIMIT 1", d=real_crop["last"])
        last3 = [r["quantity"] for r in sql(
            "SELECT quantity FROM Harvest WHERE crop_id = :c AND "
            "harvest_date < :d ORDER BY harvest_date DESC, harvest_id DESC "
            "LIMIT 3", c=real_crop["crop_id"], d=real_crop["last"])]
        status, body, _, _, _ = http("POST", "/forecasts/generate", {
            "crop_id": real_crop["crop_id"],
            "season_id": season_row["season_id"],
            "forecast_date": real_crop["last"].isoformat()
            if hasattr(real_crop["last"], "isoformat") else real_crop["last"]})
        got = (body or {}).get("calculation", {}).get("estimated_quantity")
        want = round(sum(last3) / 3, 2) if len(last3) == 3 else None
        check("FR-07", "FR-07-06", "Preview on REAL history of crop "
              f"#{real_crop['crop_id']} equals an independent SQL "
              "computation", want, got, status == 200 and got == want)
    stored = [f for f in http("GET", "/forecasts")[1]["forecasts"]
              if f["method"].startswith("Moving Average (3")]
    reproduced, refused = 0, []
    for forecast in stored:
        rows = [r["quantity"] for r in sql(
            "SELECT quantity FROM Harvest WHERE crop_id = :c AND "
            "harvest_date < :d ORDER BY harvest_date DESC, harvest_id DESC "
            "LIMIT 3", c=forecast["crop_id"], d=forecast["forecast_date"])]
        if len(rows) == 3 and round(sum(rows) / 3, 2) == \
                forecast["estimated_quantity"]:
            reproduced += 1
        else:
            refused.append(forecast["forecast_id"])
    check("FR-07", "FR-07-07", "The documented method (SQL recomputation) "
          "reproduces every stored 'Moving Average (3 records)' forecast",
          len(stored), reproduced, reproduced == len(stored),
          not_reproduced=refused)

    # FR-08 store + compare with a subsequent actual harvest
    status, body, _, _, _ = generate(crop_a, s2, f"{PAST_YEAR}-05-08",
                                     save=True)
    saved = (body or {}).get("forecast")
    if saved:
        CREATED["Forecast"].append(saved["forecast_id"])
    db_row = sql_one("SELECT * FROM Forecast WHERE forecast_id = :f",
                     f=(saved or {}).get("forecast_id", -1))
    check("FR-08", "FR-08-01", "Generated forecast is persisted",
          "row in Forecast", jsonable(db_row) if db_row else None,
          status == 201 and db_row is not None
          and float(db_row["estimated_quantity"]) == round(
              (1300 + 1600 + 1250) / 3, 2))
    item = http("GET", f"/forecasts/{saved['forecast_id']}")[1]["forecast"] \
        if saved else {}
    ev = item.get("evaluation") or {}
    check("FR-08", "FR-08-02", "Retrieved forecast is Pending before any "
          "actual harvest", "Pending / actual None",
          f"{ev.get('forecast_status')} / {ev.get('actual_quantity')}",
          ev.get("forecast_status") == "Pending"
          and ev.get("actual_quantity") is None)
    actual = make("/harvests", {"crop_id": crop_a["crop_id"],
                                "season_id": s2["season_id"],
                                "harvest_date": f"{PAST_YEAR}-05-08",
                                "quantity": 1500}, "Harvest", "harvest_id")
    item = http("GET", f"/forecasts/{saved['forecast_id']}")[1]["forecast"]
    ev = item.get("evaluation") or {}
    est = item["estimated_quantity"]
    check("FR-08", "FR-08-03", "After the actual harvest the forecast is "
          "Evaluated with the correct absolute error",
          {"status": "Evaluated", "actual": 1500,
           "absolute_error": round(abs(1500 - est), 2)},
          {"status": ev.get("forecast_status"),
           "actual": ev.get("actual_quantity"),
           "absolute_error": ev.get("absolute_error")},
          ev.get("forecast_status") == "Evaluated"
          and ev.get("actual_quantity") == 1500
          and abs(ev.get("absolute_error") - abs(1500 - est)) < 0.01,
          actual_harvest_id=actual["harvest_id"])
    status_rows = http("GET", "/forecasts/status")[1]["rows"]
    summary = http("GET", "/forecasts/summary")[1]["rows"][0]
    evaluated = [r for r in status_rows
                 if r["forecast_status"] == "Evaluated"]
    mae = round(sum(r["absolute_error"] for r in evaluated) /
                len(evaluated), 2)
    mape = round(sum(abs(r["actual_quantity"] - r["estimated_quantity"]) /
                     r["actual_quantity"] * 100 for r in evaluated) /
                 len(evaluated), 2)
    check("FR-08", "FR-08-04", "vw_forecast_summary MAE/MAPE equal an "
          "independent computation from vw_forecast_status",
          {"MAE": mae, "MAPE": mape, "total": len(status_rows)},
          {"MAE": summary["MAE"], "MAPE": summary["MAPE"],
           "total": summary["total_forecasts"]},
          abs(summary["MAE"] - mae) < 0.011
          and abs(summary["MAPE"] - mape) < 0.011
          and summary["total_forecasts"] == len(status_rows))

    # FR-09 referential integrity through the API
    before = counts()
    bad = [
        ("POST", "/lots", {"farm_id": 999999999, "name": "x", "area": 1}),
        ("POST", "/crops", {"lot_id": 999999999,
                            "variety_id": var_a["variety_id"],
                            "planting_date": "2000-01-01"}),
        ("POST", "/harvests", {"crop_id": crop_a["crop_id"],
                               "season_id": 999999999,
                               "harvest_date": f"{PAST_YEAR}-02-03",
                               "quantity": 1}),
        ("POST", "/forecasts", {"crop_id": 999999999,
                                "season_id": s1["season_id"],
                                "forecast_date": f"{PAST_YEAR}-02-10",
                                "estimated_quantity": 1, "method": "x"}),
        ("PUT", f"/harvests/{harvests[0]['harvest_id']}",
         {"crop_id": 999999999, "season_id": s1["season_id"],
          "harvest_date": f"{PAST_YEAR}-02-02", "quantity": 1000}),
    ]
    statuses = [http(m, p, b)[0] for m, p, b in bad]
    check("FR-09", "FR-09-01", "Invalid references refused by the API "
          "(Lot->Farm, Crop->Lot, Harvest->Season, Forecast->Crop, update "
          "Harvest->Crop)", [400] * len(bad), statuses,
          statuses == [400] * len(bad))
    deletes = [http("DELETE", f"/farms/{farm['farm_id']}")[0],
               http("DELETE", f"/varieties/{var_a['variety_id']}")[0],
               http("DELETE", f"/seasons/{s1['season_id']}")[0],
               http("DELETE", f"/crops/{crop_a['crop_id']}")[0]]
    check("FR-09", "FR-09-02", "Parents with dependants cannot be deleted "
          "(Farm, RoseVariety, Season, Crop)", [409] * 4, deletes,
          deletes == [409] * 4)
    check("FR-09", "FR-09-03", "Database unchanged by refused operations",
          before, counts(), before == counts())

    # FR-01 / FR-02 / FR-04 behaviours not covered by the CRUD matrix
    detail = http("GET", f"/farms/{farm['farm_id']}")[1]["farm"]
    check("FR-02", "FR-02-01", "Lots are associated with their farm (farm "
          "detail lists them)", sorted([lot_a["lot_id"], lot_b["lot_id"]]),
          sorted(l["lot_id"] for l in detail["lots"]),
          sorted(l["lot_id"] for l in detail["lots"]) ==
          sorted([lot_a["lot_id"], lot_b["lot_id"]]))
    status = http("PUT", f"/seasons/{s1['season_id']}", {
        "name": s1["name"], "start_date": f"{PAST_YEAR}-02-03",
        "end_date": f"{PAST_YEAR}-02-14"})[0]
    check("FR-04", "FR-04-01", "A season cannot be shrunk so that its "
          "harvests fall outside it", 409, status, status == 409)
    status, body = http("POST", "/varieties",
                        {"name": var_a["name"].lower(), "color": "White"})[:2]
    check("FR-01", "FR-01-01", "A second variety with the same name (any "
          "colour, any case) is refused (rule of 2026-11-23)", "409 "
          "DUPLICATE_RECORD", f"{status} {(body or {}).get('code')}",
          status == 409 and (body or {}).get("code") == "DUPLICATE_RECORD")


# ----------------------------------------------------------------------
# 7b. Duplicate prevention (2026-11-23)
# ----------------------------------------------------------------------

def section_duplicates():
    """Every rule through the running API, with SQL counts before/after,
    plus 8 truly concurrent identical requests per entity."""
    import threading

    def count(query, **params):
        return sql_one(query, **params)["n"]

    def dup_case(check_id, entity, path, body, variants, legit, where,
                 params):
        before = count(where, **params)
        results = [http("POST", path, v)[:2] for v in [body] + variants]
        after = count(where, **params)
        codes = [f"{s} {(b or {}).get('code', '')}".strip()
                 for s, b in results]
        ok = all(c == "409 DUPLICATE_RECORD" for c in codes) and \
            after == before
        check("DUP", check_id, f"{entity}: exact and normalized duplicates "
              f"refused, no row added", f"409 x {len(codes)}, count "
              f"{before}", f"{codes}, count {before} -> {after}", ok)
        if legit is not None:
            status, created = http("POST", path, legit)[:2]
            if status == 201:
                item = next(v for v in created.values() if isinstance(v,
                                                                     dict))
                table = {"/farms": "Farm", "/lots": "Lot",
                         "/varieties": "RoseVariety", "/crops": "Crop",
                         "/seasons": "Season", "/harvests": "Harvest",
                         "/forecasts": "Forecast"}[path]
                CREATED[table].append(item[TABLES[table]])
            check("DUP", check_id + "L", f"{entity}: legitimate similar "
                  f"record accepted", 201, status, status == 201)

    def race(check_id, entity, path, body, table, where, params, n=8):
        before = count(where, **params)
        barrier = threading.Barrier(n)
        out, lock = [], threading.Lock()

        def worker():
            barrier.wait()
            status, response = http("POST", path, body)[:2]
            with lock:
                out.append((status, response))
        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        for status, response in out:
            if status == 201:
                item = next(v for v in response.values()
                            if isinstance(v, dict))
                CREATED[table].append(item[TABLES[table]])
        after = count(where, **params)
        statuses = sorted(f"{s} {(r or {}).get('code', '')}".strip()
                          for s, r in out)
        ok = statuses.count("201") == 1 and after == before + 1
        check("DUP", check_id, f"{entity}: {n} identical concurrent POSTs "
              f"create exactly one row", f"1 x 201, count +1",
              f"{statuses}, count {before} -> {after}", ok)

    # database constraints present
    found = {r["CONSTRAINT_NAME"] for r in sql(
        "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'UNIQUE'")}
    wanted = {"unique_farm_name_location", "unique_lot_farm_name",
              "unique_season_name_dates", "unique_harvest_crop_date",
              "unique_crop_forecast_date"}
    check("DUP", "DUP-DB", "UNIQUE constraints present in the database",
          sorted(wanted), sorted(found & wanted), wanted <= found)

    farm = make("/farms", {"name": f"{TAG}_DupFarm", "location": "Cayambe"},
                "Farm", "farm_id")
    dup_case("DUP-01", "Farm", "/farms",
             {"name": f"{TAG}_DupFarm", "location": "Cayambe"},
             [{"name": f"  {TAG.lower()}_dupfarm ", "location": "CAYAMBE"}],
             {"name": f"{TAG}_DupFarm", "location": "Tabacundo"},
             "SELECT COUNT(*) n FROM Farm WHERE name LIKE :p",
             {"p": f"{TAG}_DupFarm%"})
    lot = make("/lots", {"farm_id": farm["farm_id"], "name": "Lot A",
                         "area": 1}, "Lot", "lot_id")
    farm2 = make("/farms", {"name": f"{TAG}_DupFarm2", "location": "x"},
                 "Farm", "farm_id")
    dup_case("DUP-02", "Lot", "/lots",
             {"farm_id": farm["farm_id"], "name": "Lot A", "area": 2},
             [{"farm_id": farm["farm_id"], "name": " lot   a ", "area": 2}],
             {"farm_id": farm2["farm_id"], "name": "Lot A", "area": 2},
             "SELECT COUNT(*) n FROM Lot WHERE farm_id = :f",
             {"f": farm["farm_id"]})
    variety = make("/varieties", {"name": f"{TAG}_DupVar", "color": "Red"},
                   "RoseVariety", "variety_id")
    dup_case("DUP-03", "RoseVariety", "/varieties",
             {"name": f"{TAG}_DupVar", "color": "Red"},
             [{"name": f"{TAG}_DupVar", "color": "White"},
              {"name": f" {TAG.upper()}_DUPVAR ", "color": "Red"}],
             None, "SELECT COUNT(*) n FROM RoseVariety WHERE name LIKE :p",
             {"p": f"{TAG}_DupVar%"})
    crop = make("/crops", {"lot_id": lot["lot_id"],
                           "variety_id": variety["variety_id"],
                           "planting_date": f"{PAST_YEAR - 1}-06-01"},
                "Crop", "crop_id")
    dup_case("DUP-04", "Crop", "/crops",
             {"lot_id": lot["lot_id"], "variety_id": variety["variety_id"],
              "planting_date": f"{PAST_YEAR - 1}-06-01"}, [],
             {"lot_id": lot["lot_id"], "variety_id": variety["variety_id"],
              "planting_date": f"{PAST_YEAR}-01-05"},
             "SELECT COUNT(*) n FROM Crop WHERE lot_id = :l",
             {"l": lot["lot_id"]})
    season = make("/seasons", {"name": f"{TAG}_DupSeason",
                               "start_date": f"{PAST_YEAR}-02-01",
                               "end_date": f"{PAST_YEAR}-02-28"},
                  "Season", "season_id")
    dup_case("DUP-05", "Season", "/seasons",
             {"name": f"{TAG}_DupSeason", "start_date": f"{PAST_YEAR}-02-01",
              "end_date": f"{PAST_YEAR}-02-28"},
             [{"name": f" {TAG.lower()}_dupseason",
               "start_date": f"{PAST_YEAR}-02-10",
               "end_date": f"{PAST_YEAR}-03-05"}],
             {"name": f"{TAG}_DupSeason", "start_date": f"{PAST_YEAR + 1}-02-01",
              "end_date": f"{PAST_YEAR + 1}-02-28"},
             "SELECT COUNT(*) n FROM Season WHERE name LIKE :p",
             {"p": f"{TAG}_DupSeason%"})
    make("/harvests", {"crop_id": crop["crop_id"],
                       "season_id": season["season_id"],
                       "harvest_date": f"{PAST_YEAR}-02-05", "quantity": 900},
         "Harvest", "harvest_id")
    dup_case("DUP-06", "Harvest", "/harvests",
             {"crop_id": crop["crop_id"], "season_id": season["season_id"],
              "harvest_date": f"{PAST_YEAR}-02-05", "quantity": 900},
             [{"crop_id": crop["crop_id"], "season_id": season["season_id"],
               "harvest_date": f"{PAST_YEAR}-02-05", "quantity": 120}],
             {"crop_id": crop["crop_id"], "season_id": season["season_id"],
              "harvest_date": f"{PAST_YEAR}-02-06", "quantity": 900},
             "SELECT COUNT(*) n FROM Harvest WHERE crop_id = :c",
             {"c": crop["crop_id"]})
    make("/forecasts", {"crop_id": crop["crop_id"],
                        "season_id": season["season_id"],
                        "forecast_date": f"{PAST_YEAR}-02-20",
                        "estimated_quantity": 7, "method": "audit"},
         "Forecast", "forecast_id")
    dup_case("DUP-07", "Forecast", "/forecasts",
             {"crop_id": crop["crop_id"], "season_id": season["season_id"],
              "forecast_date": f"{PAST_YEAR}-02-20",
              "estimated_quantity": 8, "method": "audit"}, [],
             {"crop_id": crop["crop_id"], "season_id": season["season_id"],
              "forecast_date": f"{PAST_YEAR}-02-21",
              "estimated_quantity": 8, "method": "audit"},
             "SELECT COUNT(*) n FROM Forecast WHERE crop_id = :c",
             {"c": crop["crop_id"]})
    status, body = http("POST", "/forecasts/generate", {
        "crop_id": crop["crop_id"], "season_id": season["season_id"],
        "forecast_date": f"{PAST_YEAR}-02-20", "window": 1,
        "save": True})[:2]
    stored = sql_one("SELECT estimated_quantity v FROM Forecast WHERE "
                     "crop_id = :c AND forecast_date = :d",
                     c=crop["crop_id"], d=f"{PAST_YEAR}-02-20")["v"]
    check("DUP", "DUP-07G", "Forecast: saving a generated forecast for an "
          "existing crop/date is refused and does not overwrite it",
          "409, stored 7.00", f"{status}, stored {stored}",
          status == 409 and float(stored) == 7.0)
    # updates: keeping own values allowed, taking another record's refused
    status = http("PUT", f"/varieties/{variety['variety_id']}",
                  {"name": f"{TAG}_DupVar", "color": "Pink"})[0]
    other = make("/varieties", {"name": f"{TAG}_DupVar2", "color": "Red"},
                 "RoseVariety", "variety_id")
    status2, body2 = http("PUT", f"/varieties/{other['variety_id']}",
                          {"name": f"{TAG}_DupVar", "color": "Red"})[:2]
    check("DUP", "DUP-08", "PUT keeping its own unique values is accepted; "
          "PUT to another record's values is refused", "200, 409",
          f"{status}, {status2}", status == 200 and status2 == 409)

    # truly concurrent identical requests against the running server
    farm_r = make("/farms", {"name": f"{TAG}_RaceFarm", "location": "x"},
                  "Farm", "farm_id")
    race("DUP-R1", "Farm", "/farms", {"name": f"{TAG}_Race", "location": "y"},
         "Farm", "SELECT COUNT(*) n FROM Farm WHERE name = :n",
         {"n": f"{TAG}_Race"})
    race("DUP-R2", "Lot", "/lots", {"farm_id": farm_r["farm_id"],
                                     "name": "Race", "area": 1}, "Lot",
         "SELECT COUNT(*) n FROM Lot WHERE farm_id = :f",
         {"f": farm_r["farm_id"]})
    race("DUP-R3", "RoseVariety", "/varieties",
         {"name": f"{TAG}_RaceVar", "color": "Red"}, "RoseVariety",
         "SELECT COUNT(*) n FROM RoseVariety WHERE name = :n",
         {"n": f"{TAG}_RaceVar"})
    race("DUP-R4", "Crop", "/crops", {"lot_id": lot["lot_id"],
                                       "variety_id": variety["variety_id"],
                                       "planting_date": f"{PAST_YEAR - 1}-09-01"},
         "Crop", "SELECT COUNT(*) n FROM Crop WHERE lot_id = :l",
         {"l": lot["lot_id"]})
    race("DUP-R5", "Season", "/seasons",
         {"name": f"{TAG}_RaceSeason", "start_date": f"{PAST_YEAR}-04-01",
          "end_date": f"{PAST_YEAR}-04-10"}, "Season",
         "SELECT COUNT(*) n FROM Season WHERE name = :n",
         {"n": f"{TAG}_RaceSeason"})
    race("DUP-R6", "Harvest", "/harvests",
         {"crop_id": crop["crop_id"], "season_id": season["season_id"],
          "harvest_date": f"{PAST_YEAR}-02-09", "quantity": 1}, "Harvest",
         "SELECT COUNT(*) n FROM Harvest WHERE crop_id = :c",
         {"c": crop["crop_id"]})
    race("DUP-R7", "Forecast", "/forecasts",
         {"crop_id": crop["crop_id"], "season_id": season["season_id"],
          "forecast_date": f"{PAST_YEAR}-02-25", "estimated_quantity": 1,
          "method": "audit race"}, "Forecast",
         "SELECT COUNT(*) n FROM Forecast WHERE crop_id = :c",
         {"c": crop["crop_id"]})


# ----------------------------------------------------------------------
# 8. Clean-up and guard
# ----------------------------------------------------------------------

def cleanup(baseline):
    with engine.begin() as conn:
        for table in DELETE_ORDER:
            ids = sorted(set(CREATED[table]) - set(baseline[table]))
            if ids:
                pk = TABLES[table]
                placeholders = ", ".join(f":i{n}" for n in range(len(ids)))
                conn.execute(text(f"DELETE FROM `{table}` WHERE `{pk}` IN "
                                  f"({placeholders})"),
                             {f"i{n}": v for n, v in enumerate(ids)})
    log(f"clean-up removed: { {t: len(v) for t, v in CREATED.items()} }")


def guard(baseline, schema_before):
    after = data_snapshot()
    problems = []
    for table, rows in baseline.items():
        for pk, digest in rows.items():
            if pk not in after[table]:
                problems.append(f"{table} {pk} deleted")
            elif after[table][pk] != digest:
                problems.append(f"{table} {pk} modified")
        for pk in after[table]:
            if pk not in rows:
                problems.append(f"{table} {pk} left behind")
    check("GUARD", "GUARD-01", "Every pre-existing row unchanged and no "
          "audit row left behind", "no difference", problems or
          "no difference", not problems,
          rows_checked=sum(len(v) for v in baseline.values()))
    schema_after = schema_fingerprint()
    check("NFR-05", "NFR-05-01", "Schema unchanged after inserting and "
          "managing new varieties, lots, crops, seasons, harvests and "
          "forecasts", schema_before, schema_after,
          schema_after == schema_before)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    log(f"Final audit {RUN_ID} against {BASE}")
    baseline = data_snapshot()
    schema_before = schema_fingerprint()
    RESULTS["baseline_rows"] = {t: len(v) for t, v in baseline.items()}
    sections = [("environment", section_environment),
                ("schema", section_schema),
                ("data_quality", section_data_quality),
                ("performance", section_performance),
                ("constraints", section_constraints),
                ("security", section_security),
                ("crud", section_crud),
                ("functional", section_functional),
                ("duplicates", section_duplicates)]
    try:
        for name, function in sections:
            log(f"--- {name}")
            try:
                function()
            except Exception as exc:  # record and continue
                RESULTS["checks"].append(redact({
                    "section": name.upper(), "id": f"{name}-ERROR",
                    "title": "section aborted", "expected": "no error",
                    "actual": f"{exc.__class__.__name__}: {exc}",
                    "result": "FAIL",
                    "trace": traceback.format_exc()[-2000:]}))
                log(f"ERROR in {name}: {exc}")
    finally:
        cleanup(baseline)
        guard(baseline, schema_before)
    RESULTS["finished_at"] = dt.datetime.now().astimezone().isoformat()
    RESULTS["created_ids"] = CREATED
    summary = {}
    for item in RESULTS["checks"]:
        summary[item["result"]] = summary.get(item["result"], 0) + 1
    RESULTS["summary"] = summary
    with open(os.path.join(OUT_DIR, "audit_results.json"), "w",
              encoding="utf-8") as handle:
        json.dump(redact(RESULTS), handle, indent=2, default=str)
    with open(os.path.join(OUT_DIR, "audit_log.txt"), "w",
              encoding="utf-8") as handle:
        handle.write(redact("\n".join(LOG_LINES)) + "\n")
    log(f"SUMMARY {summary}")
    return 0 if summary.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
