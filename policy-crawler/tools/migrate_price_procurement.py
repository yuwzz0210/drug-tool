# -*- coding: utf-8 -*-
"""Step-2 migration: rebuild price_history with region/batch/flag dimensions and
create procurement_result (nullable product_id for pre-registration rows).

Backs up the DB file first. Idempotent: skips work already applied.

Usage:
    python tools/migrate_price_procurement.py --db policy_crawler.db
"""
import argparse
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models import DRUG_SCHEMA  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def columns(db, table):
    return {r[1] for r in db.execute("PRAGMA table_info(%s)" % table)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    args = ap.parse_args()
    backup = args.db + ".bak_price_procurement"
    if not os.path.exists(backup):
        shutil.copy(args.db, backup)
        print("backup ->", backup)

    db = sqlite3.connect(args.db)
    try:
        cols = columns(db, "price_history")
        need_rebuild = "region" not in cols
        if need_rebuild:
            rows = db.execute(
                """SELECT product_id, price_type, price, unit, effective_date,
                          expire_date, source_url, reviewed_at, reviewed_by,
                          notes, created_at FROM price_history""").fetchall()
            db.execute("BEGIN")
            db.execute("ALTER TABLE price_history RENAME TO price_history_old")
            # recreate with the new schema inside the same transaction
            db.execute("""CREATE TABLE price_history (
                price_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL
                    REFERENCES drug_product(product_id) ON DELETE CASCADE,
                price_type TEXT NOT NULL DEFAULT '挂网',
                price REAL NOT NULL,
                unit TEXT DEFAULT '',
                region TEXT DEFAULT '',
                batch TEXT DEFAULT '',
                price_flag TEXT DEFAULT '',
                effective_date TEXT DEFAULT '',
                expire_date TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                reviewed_at TEXT DEFAULT '',
                reviewed_by TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE (product_id, price_type, region, batch, effective_date)
            )""")
            for r in rows:
                db.execute(
                    """INSERT INTO price_history
                       (product_id, price_type, price, unit, region, batch,
                        price_flag, effective_date, expire_date, source_url,
                        reviewed_at, reviewed_by, notes, created_at)
                       VALUES (?,?,?,?,'','','',?,?,?,?,?,?,?)""", r)
            db.execute("DROP TABLE price_history_old")
            db.execute("COMMIT")
            print("price_history rebuilt; copied rows:", len(rows))
        else:
            print("price_history already migrated")

        db.executescript(DRUG_SCHEMA)
        n_price = db.execute(
            "SELECT COUNT(*) FROM price_history").fetchone()[0]
        n_proc = db.execute(
            "SELECT COUNT(*) FROM procurement_result").fetchone()[0]
        print("price_history rows:", n_price,
              "| procurement_result rows:", n_proc)
    except Exception as exc:
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass
        print("MIGRATION_FAILED", repr(exc))
        return 1
    finally:
        db.close()
    print("MIGRATION_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
