# -*- coding: utf-8 -*-
"""Problem-1 migration: make drug_leaflet unique by (product_id, catalog_rid).

Before this migration, rows without a real approval number used synthetic
"PM:xxxxx" approval numbers to satisfy UNIQUE(approval_number, catalog_rid).
That polluted the approval_number column. After migration:
  * approval_number only ever holds a real 国药准字/注册证号 (or '');
  * uniqueness is per product + CDE source record (catalog_rid);
  * synthetic PM: keys are cleared.

SQLite cannot alter a table-level UNIQUE constraint, so the table is rebuilt
inside one transaction (rollback on any failure). Run a DB backup first.

Usage:
    python tools/migrate_leaflet_key.py --db policy_crawler.db
"""
import argparse
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    args = ap.parse_args()

    db = sqlite3.connect(args.db)
    db.execute("PRAGMA foreign_keys=OFF")
    try:
        # sanity: no duplicates under the new key before we rebuild
        dups = db.execute("""
            SELECT product_id, catalog_rid, COUNT(*)
            FROM drug_leaflet
            GROUP BY product_id, catalog_rid
            HAVING COUNT(*) > 1""").fetchall()
        if dups:
            print("ABORT duplicates under (product_id, catalog_rid):", dups[:5])
            return 2
        total_before = db.execute(
            "SELECT COUNT(*) FROM drug_leaflet").fetchone()[0]
        pm_before = db.execute(
            "SELECT COUNT(*) FROM drug_leaflet "
            "WHERE approval_number LIKE 'PM:%'").fetchone()[0]

        db.execute("BEGIN")
        db.execute("""CREATE TABLE drug_leaflet_new (
            leaflet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL
                REFERENCES drug_product(product_id) ON DELETE CASCADE,
            approval_number TEXT DEFAULT '',
            catalog_rid TEXT DEFAULT '',
            pdf_url TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            filename TEXT DEFAULT '',
            route TEXT DEFAULT '',
            storage TEXT DEFAULT '',
            cold_chain TEXT DEFAULT '',
            usage_dosage TEXT DEFAULT '',
            indications TEXT DEFAULT '',
            leaflet_date TEXT DEFAULT '',
            sections_json TEXT DEFAULT '{}',
            raw_text TEXT DEFAULT '',
            fetched_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE (product_id, catalog_rid)
        )""")
        db.execute("""
            INSERT INTO drug_leaflet_new (
                leaflet_id, product_id, approval_number, catalog_rid,
                pdf_url, source_url, filename, route, storage, cold_chain,
                usage_dosage, indications, leaflet_date, sections_json,
                raw_text, fetched_at, updated_at)
            SELECT leaflet_id, product_id,
                   CASE WHEN approval_number LIKE 'PM:%'
                        THEN '' ELSE approval_number END,
                   catalog_rid, pdf_url, source_url, filename, route, storage,
                   cold_chain, usage_dosage, indications, leaflet_date,
                   sections_json, raw_text, fetched_at, updated_at
            FROM drug_leaflet""")
        db.execute("DROP TABLE drug_leaflet")
        db.execute("ALTER TABLE drug_leaflet_new RENAME TO drug_leaflet")
        db.execute("COMMIT")

        total_after = db.execute(
            "SELECT COUNT(*) FROM drug_leaflet").fetchone()[0]
        pm_after = db.execute(
            "SELECT COUNT(*) FROM drug_leaflet "
            "WHERE approval_number LIKE 'PM:%'").fetchone()[0]
        # integrity check
        bad = db.execute("""
            SELECT COUNT(*) FROM drug_leaflet l
            WHERE NOT EXISTS (
                SELECT 1 FROM drug_product p WHERE p.product_id = l.product_id)
        """).fetchone()[0]
        print("total %d -> %d | pm_keys %d -> %d | orphan_rows %d"
              % (total_before, total_after, pm_before, pm_after, bad))
        if total_before != total_after or pm_after != 0 or bad:
            print("VERIFY FAILED - restore backup and inspect")
            return 3
        print("MIGRATION_OK")
        return 0
    except Exception as exc:
        db.execute("ROLLBACK")
        print("MIGRATION_FAILED", repr(exc))
        return 1
    finally:
        db.execute("PRAGMA foreign_keys=ON")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
