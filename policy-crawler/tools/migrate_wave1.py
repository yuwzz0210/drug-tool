# -*- coding: utf-8 -*-
"""Wave-1 迁移：病种/领域分类列 + 国谈结果表 + 双通道表。

改动内容（幂等，可重复执行）：
1) drug_molecule 增加 therapeutic_area / disease / sub_disease /
   classification_source / classification_confidence 五列；
2) 新建 negotiation_result（国谈/竞价结果）与 dual_channel（双通道名单）；
3) 建索引：按 product_id 回挂、按分子领域筛选。

执行前自动备份数据库（备份文件已存在则不覆盖）。

用法：
    python tools/migrate_wave1.py --db policy_crawler.db
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


MOLECULE_COLUMNS = (
    ("therapeutic_area", "TEXT DEFAULT ''"),
    ("disease", "TEXT DEFAULT ''"),
    ("sub_disease", "TEXT DEFAULT ''"),
    ("classification_source", "TEXT DEFAULT ''"),
    ("classification_confidence", "TEXT DEFAULT ''"),
)

# 表结构补列（表已存在时使用；新表在 NEW_TABLES 中已含这些列）
LINK_COLUMNS = (
    ("negotiation_result", "molecule_id",
     "INTEGER REFERENCES drug_molecule(molecule_id) ON DELETE SET NULL"),
    ("dual_channel", "molecule_id",
     "INTEGER REFERENCES drug_molecule(molecule_id) ON DELETE SET NULL"),
)

NEW_TABLES = {
    "negotiation_result": """
        CREATE TABLE IF NOT EXISTS negotiation_result (
            negotiation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER REFERENCES drug_product(product_id)
                ON DELETE SET NULL,
            catalog_id INTEGER REFERENCES insurance_catalog(catalog_id),
            catalog_entry_id INTEGER,
            batch_year TEXT DEFAULT '',
            drug_name TEXT NOT NULL,
            dosage_form TEXT DEFAULT '',
            category TEXT DEFAULT '',
            pay_standard TEXT DEFAULT '',
            agreement_period TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE (catalog_entry_id)
        )""",
    "dual_channel": """
        CREATE TABLE IF NOT EXISTS dual_channel (
            dual_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER REFERENCES drug_product(product_id)
                ON DELETE SET NULL,
            region TEXT NOT NULL DEFAULT '国家',
            drug_name TEXT NOT NULL,
            dosage_form TEXT DEFAULT '',
            specification TEXT DEFAULT '',
            status TEXT DEFAULT '纳入',
            effective_date TEXT DEFAULT '',
            batch TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE (region, drug_name, dosage_form, specification)
        )""",
}

INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_negotiation_product "
    "ON negotiation_result(product_id)",
    "CREATE INDEX IF NOT EXISTS ix_negotiation_name "
    "ON negotiation_result(drug_name)",
    "CREATE INDEX IF NOT EXISTS ix_dual_channel_product "
    "ON dual_channel(product_id)",
    "CREATE INDEX IF NOT EXISTS ix_dual_channel_region_name "
    "ON dual_channel(region, drug_name)",
    "CREATE INDEX IF NOT EXISTS ix_molecule_area "
    "ON drug_molecule(therapeutic_area)",
)


def cols(db, table):
    return {r[1] for r in db.execute("PRAGMA table_info(%s)" % table)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Wave-1 迁移")
    ap.add_argument("--db", default="policy_crawler.db")
    args = ap.parse_args(argv)

    backup = args.db + ".bak_wave1"
    if not os.path.exists(backup):
        shutil.copy(args.db, backup)
        print("backup ->", backup)
    else:
        print("backup exists ->", backup)

    db = sqlite3.connect(args.db)
    try:
        added = []
        existing = cols(db, "drug_molecule")
        for name, ddl in MOLECULE_COLUMNS:
            if name not in existing:
                db.execute(
                    "ALTER TABLE drug_molecule ADD COLUMN %s %s" % (name, ddl))
                added.append(name)
        created = []
        for name, ddl in NEW_TABLES.items():
            if not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (name,)).fetchone():
                db.execute(ddl)
                created.append(name)
        for table, name, ddl in LINK_COLUMNS:
            if name not in cols(db, table):
                db.execute("ALTER TABLE %s ADD COLUMN %s %s"
                           % (table, name, ddl))
                added.append("%s.%s" % (table, name))
        for stmt in INDEXES:
            db.execute(stmt)
        db.commit()

        print("columns added:", added or "none")
        print("tables created:", created or "none")
        print("drug_molecule columns:",
              len(db.execute("PRAGMA table_info(drug_molecule)").fetchall()))
        for name in ("negotiation_result", "dual_channel"):
            print(name, "rows:",
                  db.execute("SELECT COUNT(*) FROM %s" % name).fetchone()[0])
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
