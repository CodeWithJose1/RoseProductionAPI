"""Sequential duplicate POSTs (same body twice, then a case/space variant)
against the scratch database RoseProductionDB_migtest2 (cloud replica copy
WITHOUT the new UNIQUE constraints), with the code given in argv[1]
(the code before the fix = the user's folder on 2026-11-23, or the fixed
code). Shows what the API alone does. TEST_ rows are deleted at the end."""
import json, os, sys, uuid
code_dir = sys.argv[1]
sys.path.insert(0, code_dir)
os.environ["DB_NAME"] = "RoseProductionDB_migtest2"
from sqlalchemy import text
from app import create_app
from models import db
app = create_app(); app.config["TESTING"] = True
H = {"X-API-Key": app.config["API_KEY"]}
c = app.test_client(); made = []
def post(path, body):
    r = c.post(path, json=body, headers=H); j = r.get_json() or {}
    if r.status_code == 201:
        k = next(k for k, v in j.items() if isinstance(v, dict)); pk = [x for x in j[k] if x.endswith("_id") and x[:-3] in (k, "variety" if k=="variety" else k)][0]
        made.append((path, j[k][pk]))
    return r.status_code, j.get("code")
u = uuid.uuid4().hex[:6]
res = {}
farm = {"name": f"TEST_BA_{u}", "location": "Cayambe"}
res["farm"] = [post("/farms", farm), post("/farms", farm), post("/farms", {"name": f"  test_ba_{u} ", "location": "cayambe"})]
fid = made[0][1]
lot = {"farm_id": fid, "name": "Lot A", "area": 1}
res["lot"] = [post("/lots", lot), post("/lots", lot), post("/lots", dict(lot, name=" lot   a "))]
var = {"name": f"TEST_BA_V_{u}", "color": "Peach"}
res["variety"] = [post("/varieties", var), post("/varieties", var), post("/varieties", dict(var, name=var["name"].upper(), color="Red"))]
lid = [i for p, i in made if p == "/lots"][0]; vid = [i for p, i in made if p == "/varieties"][0]
crop = {"lot_id": lid, "variety_id": vid, "planting_date": "2000-06-01"}
res["crop"] = [post("/crops", crop), post("/crops", crop)]
season = {"name": f"TEST_BA_S_{u}", "start_date": "2001-02-01", "end_date": "2001-02-28"}
res["season"] = [post("/seasons", season), post("/seasons", season), post("/seasons", dict(season, name=f" test_ba_s_{u}", start_date="2001-02-10"))]
cid = [i for p, i in made if p == "/crops"][0]; sid = [i for p, i in made if p == "/seasons"][0]
h = {"crop_id": cid, "season_id": sid, "harvest_date": "2001-02-05", "quantity": 10}
res["harvest"] = [post("/harvests", h), post("/harvests", h)]
f = {"crop_id": cid, "season_id": sid, "forecast_date": "2001-02-20", "estimated_quantity": 1, "method": "x"}
res["forecast"] = [post("/forecasts", f), post("/forecasts", f)]
with app.app_context():
    with db.engine.begin() as conn:
        order = ["/forecasts", "/harvests", "/crops", "/seasons", "/lots", "/varieties", "/farms"]
        tbl = {"/forecasts": ("Forecast", "forecast_id"), "/harvests": ("Harvest", "harvest_id"), "/crops": ("Crop", "crop_id"), "/seasons": ("Season", "season_id"), "/lots": ("Lot", "lot_id"), "/varieties": ("RoseVariety", "variety_id"), "/farms": ("Farm", "farm_id")}
        for p in order:
            for path, i in made:
                if path == p: conn.execute(text(f"DELETE FROM {tbl[p][0]} WHERE {tbl[p][1]} = :i"), {"i": i})
print(json.dumps({"code": code_dir, "results": {k: [f"{s} {c or ''}".strip() for s, c in v] for k, v in res.items()}}))
