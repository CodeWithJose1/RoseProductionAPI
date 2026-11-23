"""Replica-only experiment: 8 identical concurrent POSTs per entity, with the
row locks enabled (normal code) and disabled (monkeypatched), 5 rounds each.
Reports status codes, error codes and how many rows were actually created.
All rows created are TEST_ rows and are deleted at the end by id."""
import json, os, sys, threading, uuid, collections
from datetime import date
sys.path.insert(0, "/home/claude/rose")
import config
if os.environ.get("EXP_ISOLATION"):
    config.Config.SQLALCHEMY_ENGINE_OPTIONS = dict(config.Config.SQLALCHEMY_ENGINE_OPTIONS, isolation_level=os.environ["EXP_ISOLATION"])
from sqlalchemy import text
from app import create_app
from models import db
import routes.varieties, routes.crops, routes.farms, routes.seasons, routes.lots, routes.harvests, routes.forecasts
from routes import common

app = create_app(); app.config["TESTING"] = True
H = {"X-API-Key": app.config["API_KEY"]}
created = collections.defaultdict(list)
client = app.test_client()

def mk(path, body, key, table, pk):
    r = client.post(path, json=body, headers=H); assert r.status_code == 201, r.get_json()
    rid = r.get_json()[key][pk]; created[table].append(rid); return rid

def scalar(sql, **p):
    with app.app_context():
        with db.engine.connect() as c: return c.execute(text(sql), p).scalar()

def race(path, body, n=8):
    barrier = threading.Barrier(n); out = []; lock = threading.Lock()
    def w():
        c = app.test_client(); barrier.wait()
        r = c.post(path, json=body, headers=H)
        with lock: out.append((r.status_code, (r.get_json() or {}).get("code")))
    ts = [threading.Thread(target=w) for _ in range(n)]
    [t.start() for t in ts]; [t.join(60) for t in ts]
    return out

def case(entity):
    u = uuid.uuid4().hex[:8]
    if entity == "farm":
        b = {"name": f"TEST_EXP_{u}", "location": "x"}; return "/farms", b, "Farm", "farm_id", "farm", ("SELECT COUNT(*) FROM Farm WHERE name=:n", {"n": b["name"]})
    if entity == "variety":
        b = {"name": f"TEST_EXP_{u}", "color": "Red"}; return "/varieties", b, "RoseVariety", "variety_id", "variety", ("SELECT COUNT(*) FROM RoseVariety WHERE name=:n", {"n": b["name"]})
    if entity == "season":
        b = {"name": f"TEST_EXP_{u}", "start_date": "2001-03-01", "end_date": "2001-03-10"}; return "/seasons", b, "Season", "season_id", "season", ("SELECT COUNT(*) FROM Season WHERE name=:n", {"n": b["name"]})
    farm = mk("/farms", {"name": f"TEST_EXP_F_{u}", "location": "x"}, "farm", "Farm", "farm_id")
    if entity == "lot":
        b = {"farm_id": farm, "name": "TEST race", "area": 1}; return "/lots", b, "Lot", "lot_id", "lot", ("SELECT COUNT(*) FROM Lot WHERE farm_id=:f", {"f": farm})
    lot = mk("/lots", {"farm_id": farm, "name": "TEST L", "area": 1}, "lot", "Lot", "lot_id")
    var = mk("/varieties", {"name": f"TEST_EXP_V_{u}", "color": "Red"}, "variety", "RoseVariety", "variety_id")
    if entity == "crop":
        b = {"lot_id": lot, "variety_id": var, "planting_date": "2000-06-01"}; return "/crops", b, "Crop", "crop_id", "crop", ("SELECT COUNT(*) FROM Crop WHERE lot_id=:l", {"l": lot})
    crop = mk("/crops", {"lot_id": lot, "variety_id": var, "planting_date": "2000-06-01"}, "crop", "Crop", "crop_id")
    season = mk("/seasons", {"name": f"TEST_EXP_S_{u}", "start_date": "2001-02-01", "end_date": "2001-02-28"}, "season", "Season", "season_id")
    if entity == "harvest":
        b = {"crop_id": crop, "season_id": season, "harvest_date": "2001-02-07", "quantity": 5}; return "/harvests", b, "Harvest", "harvest_id", "harvest", ("SELECT COUNT(*) FROM Harvest WHERE crop_id=:c", {"c": crop})
    b = {"crop_id": crop, "season_id": season, "forecast_date": "2001-02-20", "estimated_quantity": 5, "method": "x"}
    return "/forecasts", b, "Forecast", "forecast_id", "forecast", ("SELECT COUNT(*) FROM Forecast WHERE crop_id=:c", {"c": crop})

ORIG = {m: (getattr(m, "lock_table", None), getattr(m, "lock_parent", None)) for m in (routes.varieties, routes.farms, routes.seasons, routes.crops, routes.lots, routes.harvests, routes.forecasts)}
def set_locks(enabled):
    for m, (lt, lp) in ORIG.items():
        if lt: m.lock_table = lt if enabled else (lambda *a, **k: None)
        if lp: m.lock_parent = lp if enabled else (lambda *a, **k: None)

report = {}
for mode in ("locks_enabled", "locks_disabled"):
    set_locks(mode == "locks_enabled")
    for entity in ("farm", "lot", "variety", "crop", "season", "harvest", "forecast"):
        rows_created, codes = [], collections.Counter()
        for _ in range(5):
            path, body, table, pk, key, (sql, p) = case(entity)
            before = scalar(sql, **p)
            res = race(path, body)
            after = scalar(sql, **p)
            rows_created.append(after - before)
            for s, c in res: codes[f"{s} {c or ''}".strip()] += 1
            with app.app_context():
                with db.engine.connect() as c:
                    if entity in ("farm", "variety", "season"):
                        ids = [r[0] for r in c.execute(text(f"SELECT {pk} FROM {table} WHERE name=:n"), {"n": body["name"]})]
                    else:
                        col = {"lot": "farm_id", "crop": "lot_id", "harvest": "crop_id", "forecast": "crop_id"}[entity]
                        ids = [r[0] for r in c.execute(text(f"SELECT {pk} FROM {table} WHERE {col}=:v"), {"v": body[col]})]
            created[table].extend(ids)
        report.setdefault(mode, {})[entity] = {"rows_created_per_round": rows_created, "responses": dict(codes)}
set_locks(True)
# clean up every TEST_ row created here, children first
with app.app_context():
    with db.engine.begin() as c:
        for table, pk in (("Forecast","forecast_id"),("Harvest","harvest_id"),("Crop","crop_id"),("Season","season_id"),("Lot","lot_id"),("RoseVariety","variety_id"),("Farm","farm_id")):
            ids = sorted(set(created[table]))
            for i in ids: c.execute(text(f"DELETE FROM {table} WHERE {pk}=:i"), {"i": i})
with app.app_context():
    with db.engine.connect() as c:
        meta = {"database": c.execute(text("SELECT DATABASE()")).scalar(),
                "isolation": c.execute(text("SELECT @@transaction_isolation")).scalar(),
                "unique_constraints": [r[0] for r in c.execute(text("SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'UNIQUE' ORDER BY 1"))]}
print(json.dumps({"meta": meta, "report": report}, indent=1))
