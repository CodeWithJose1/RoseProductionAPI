#!/usr/bin/env python3
"""Compare RoseProductionDB with an isolated restored copy (read-only).

Usage: compare_restore.py <restored_db> <dump_file> <dump_s> <restore_s>
Prints a JSON report (no secrets).
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text  # noqa: E402

from config import Config  # noqa: E402

TABLES = ["Farm", "Lot", "RoseVariety", "Crop", "Season", "Harvest",
          "Forecast"]


def describe(conn, schema):
    def rows(query):
        return [tuple(r) for r in conn.execute(text(query),
                                               {"s": schema}).all()]
    info = {
        "tables": rows("SELECT TABLE_NAME FROM information_schema.TABLES "
                       "WHERE TABLE_SCHEMA = :s AND TABLE_TYPE = "
                       "'BASE TABLE' ORDER BY 1"),
        "views": rows("SELECT TABLE_NAME FROM information_schema.VIEWS "
                      "WHERE TABLE_SCHEMA = :s ORDER BY 1"),
        "triggers": rows("SELECT TRIGGER_NAME, EVENT_MANIPULATION, "
                         "ACTION_TIMING FROM information_schema.TRIGGERS "
                         "WHERE TRIGGER_SCHEMA = :s ORDER BY 1"),
        "routines": rows("SELECT ROUTINE_NAME FROM information_schema."
                         "ROUTINES WHERE ROUTINE_SCHEMA = :s ORDER BY 1"),
        "constraints": rows("SELECT TABLE_NAME, CONSTRAINT_NAME, "
                            "CONSTRAINT_TYPE FROM information_schema."
                            "TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = :s "
                            "ORDER BY 1, 2"),
        "indexes": rows("SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, "
                        "COLUMN_NAME FROM information_schema.STATISTICS "
                        "WHERE TABLE_SCHEMA = :s ORDER BY 1, 2, 3"),
        "columns": rows("SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, "
                        "IS_NULLABLE FROM information_schema.COLUMNS WHERE "
                        "TABLE_SCHEMA = :s AND TABLE_NAME IN ('Farm','Lot',"
                        "'RoseVariety','Crop','Season','Harvest','Forecast')"
                        " ORDER BY 1, 2"),
    }
    counts, digests = {}, {}
    for table in TABLES:
        data = conn.execute(text(
            f"SELECT * FROM `{schema}`.`{table}` ORDER BY 1")).all()
        counts[table] = len(data)
        digests[table] = hashlib.sha256(
            repr([tuple(map(str, r)) for r in data]).encode()).hexdigest()
    views = {}
    for (view,) in info["views"]:
        data = conn.execute(text(
            f"SELECT * FROM `{schema}`.`{view}`")).all()
        views[view] = hashlib.sha256(repr(sorted(
            tuple(map(str, r)) for r in data)).encode()).hexdigest()
    return info, counts, digests, views


def main():
    restored, dump, dump_s, restore_s = sys.argv[1:5]
    source = Config.SQLALCHEMY_DATABASE_URI.rsplit("/", 1)[1]
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    with engine.connect() as conn:
        src = describe(conn, source)
        dst = describe(conn, restored)
    keys = ["tables", "views", "triggers", "routines", "constraints",
            "indexes", "columns"]
    structure = {k: src[0][k] == dst[0][k] for k in keys}
    report = {
        "source_database": source,
        "restored_database": restored,
        "dump_file": dump,
        "dump_bytes": os.path.getsize(dump),
        "dump_sha256": hashlib.sha256(open(dump, "rb").read()).hexdigest(),
        "dump_seconds": round(float(dump_s), 3),
        "restore_seconds": round(float(restore_s), 3),
        "source": {"tables": len(src[0]["tables"]),
                   "views": len(src[0]["views"]),
                   "triggers": len(src[0]["triggers"]),
                   "routines": len(src[0]["routines"]),
                   "row_counts": src[1], "total_rows": sum(src[1].values())},
        "restored": {"tables": len(dst[0]["tables"]),
                     "views": len(dst[0]["views"]),
                     "triggers": len(dst[0]["triggers"]),
                     "routines": len(dst[0]["routines"]),
                     "row_counts": dst[1],
                     "total_rows": sum(dst[1].values())},
        "structure_equal": structure,
        "table_data_equal": {t: src[2][t] == dst[2][t] for t in TABLES},
        "view_results_equal": {v: src[3].get(v) == dst[3].get(v)
                               for v in src[3]},
    }
    report["result"] = "PASS" if (
        all(structure.values()) and all(report["table_data_equal"].values())
        and all(report["view_results_equal"].values())
        and src[1] == dst[1]) else "FAIL"
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
