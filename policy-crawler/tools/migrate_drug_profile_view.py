# -*- coding: utf-8 -*-
"""(Re)create the drug_profile v1 view on an existing database.

Non-destructive: only drops/recreates the view (no table data touched).

Usage:
    python tools/migrate_drug_profile_view.py --db policy_crawler.db
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models import DRUG_PROFILE_VIEW_SQL  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    args = ap.parse_args()
    db = sqlite3.connect(args.db)
    db.executescript("DROP VIEW IF EXISTS drug_profile;\n" + DRUG_PROFILE_VIEW_SQL)
    n = db.execute("SELECT COUNT(*) FROM drug_profile").fetchone()[0]
    cols = [r[1] for r in db.execute("PRAGMA table_info(drug_profile)")]
    print("drug_profile rows:", n, "| cols:", len(cols))
    db.close()
    print("VIEW_MIGRATION_OK")


if __name__ == "__main__":
    main()
