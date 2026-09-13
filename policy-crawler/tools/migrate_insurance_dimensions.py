# -*- coding: utf-8 -*-
"""Step-3 migration: insurance tables gain region / catalog type / reimbursement
dimensions, with an idempotency key (product, catalog, region, code).

Backs up the DB first. Existing duplicate links (same key) are deduped by
keeping the newest entry_id; the number removed is reported.

Usage:
    python tools/migrate_insurance_dimensions.py --db policy_crawler.db
"""
import argparse
import os
import shutil
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def cols(db, table):
    return {r[1] for r in db.execute("PRAGMA table_info(%s)" % table)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    args = ap.parse_args()
    backup = args.db + ".bak_insurance_dims"
    if not os.path.exists(backup):
        shutil.copy(args.db, backup)
        print("backup ->", backup)

    db = sqlite3.connect(args.db)
    try:
        cat_cols = cols(db, "insurance_catalog")
        ent_cols = cols(db, "drug_insurance_entry")
        if "region" not in cat_cols:
            db.execute("ALTER TABLE insurance_catalog "
                       "ADD COLUMN region TEXT DEFAULT '国家'")
        if "catalog_type" not in cat_cols:
            db.execute("ALTER TABLE insurance_catalog "
                       "ADD COLUMN catalog_type TEXT DEFAULT '国家医保药品目录'")
        for col, ddl in (
            ("region", "TEXT DEFAULT '国家'"),
            ("reimbursement_ratio", "TEXT DEFAULT ''"),
            ("supplement_status", "TEXT DEFAULT ''"),
            ("source_url", "TEXT DEFAULT ''"),
            ("notes", "TEXT DEFAULT ''"),
        ):
            if col not in ent_cols:
                db.execute("ALTER TABLE drug_insurance_entry "
                           "ADD COLUMN %s %s" % (col, ddl))
        db.execute("UPDATE drug_insurance_entry SET region='国家' "
                   "WHERE region IS NULL OR region=''")

        dups = db.execute("""
            SELECT product_id, catalog_id, region, insurance_code,
                   COUNT(*) c, MAX(entry_id) keep_id
            FROM drug_insurance_entry
            GROUP BY product_id, catalog_id, region, insurance_code
            HAVING c > 1""").fetchall()
        removed = 0
        if dups:
            for pid, cid, region, code, cnt, keep in dups:
                cur = db.execute("""
                    DELETE FROM drug_insurance_entry
                    WHERE product_id=? AND catalog_id=? AND region=?
                      AND insurance_code=? AND entry_id<>?""",
                    (pid, cid, region, code, keep))
                removed += cur.rowcount
        # A product may legitimately map to several catalog entries sharing the
        # same insurance code (e.g. different dosage-form rows). Idempotency is
        # guaranteed by the importer's delete-then-insert, so use a plain index.
        db.execute("DROP INDEX IF EXISTS ux_insurance_product_catalog_region_code")
        db.execute("""CREATE INDEX IF NOT EXISTS ix_insurance_key
            ON drug_insurance_entry
               (product_id, catalog_id, region, insurance_code)""")
        db.execute("""CREATE INDEX IF NOT EXISTS ix_insurance_code
            ON drug_insurance_entry(insurance_code)""")
        db.commit()
        n = db.execute(
            "SELECT COUNT(*) FROM drug_insurance_entry").fetchone()[0]
        print("dup groups:", len(dups), "| rows removed:", removed)
        print("drug_insurance_entry rows:", n)
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
