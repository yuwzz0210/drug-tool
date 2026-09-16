# -*- coding: utf-8 -*-
"""drug_profile 视图升级到 v2（预聚合 CTE）+ 建索引 + 计时验证。

非破坏性：只建索引、重建视图，不动任何表数据。

用法：
    python tools/migrate_profile_view_v2.py --db policy_crawler.db
"""
import argparse
import io
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from drug_profile_view import DRUG_PROFILE_INDEXES, DRUG_PROFILE_VIEW_SQL_V2  # noqa: E402

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="drug_profile v2 迁移")
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--limit", type=int, default=0,
                    help=">0 时仅取前 N 行做计时抽样")
    args = ap.parse_args(argv)

    db = sqlite3.connect(args.db)
    created = 0
    for stmt in DRUG_PROFILE_INDEXES:
        db.execute(stmt)
        created += 1
    db.commit()
    print("索引就绪:", created)

    db.executescript("DROP VIEW IF EXISTS drug_profile;\n"
                     + DRUG_PROFILE_VIEW_SQL_V2)
    db.commit()

    sql = "SELECT COUNT(*) FROM drug_profile"
    if args.limit:
        sql = "SELECT COUNT(*) FROM (SELECT * FROM drug_profile LIMIT %d)" % args.limit
    t0 = time.time()
    rows = db.execute(sql).fetchone()[0]
    elapsed = time.time() - t0
    print("视图行数:", rows, "| 耗时: %.2fs" % elapsed)

    t0 = time.time()
    full = db.execute("SELECT COUNT(*) FROM drug_profile").fetchone()[0]
    print("全量扫描: %d 行 | %.2fs" % (full, time.time() - t0))
    db.close()
    print("VIEW_V2_MIGRATION_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
