# -*- coding: utf-8 -*-
"""品种充盈：把省级官方公开表（含批准文号）导入 drug_molecule/product/registration。

数据来源：湖南《2026年二季度湖南省药品价格信息公布表》（说明中标注"已挂网且有效"），
每行含 批准文号/产品名称/剂型/规格/生产企业/药品统一编码。这是官方公开数据，
不含个人隐私，且带明确来源可追溯。

身份牌规则（沿用既有硬规则）：
- 以「批准文号」为唯一身份牌：已存在的文号一律不覆盖，只计数；
- 一个批准文号对应一条 registration（多规格的极少数情况取首个规格为代表，
  并在 extra_data 记录 spec_count，不制造无文号的孤儿品种）；
- 缺文号或缺名称的行整行拒绝，计入 skipped_invalid。

分子层：按 normalize.molecule_key 归一出通用名词干，缺失则新建 molecule。
价格/双通道等字段不在本工具范围内（由对应导入器负责）。

用法：
    python tools/import_public_registry.py --db policy_crawler.db \
        --source hunan --xlsx logs/regional/hunan_2026q2_price.xlsx --dry-run
"""
import argparse
import collections
import io
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

import xlsx_lite  # noqa: E402
from normalize import (  # noqa: E402
    molecule_key,
    norm_roman,
    strip_class_markers,
    strip_dosage_form,
    to_half_width,
)

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

SOURCE_URL = ("http://ybj.hunan.gov.cn/ybj/first113541/firstF/info1/202608/"
              "t20260806_34040891.html")
SOURCE_NOTE = "湖南省2026年二季度药品价格信息公布表（官方已挂网有效数据）"

# 湖南表剂型 -> 本库习惯剂型（仅做口径统一，不改变事实）
FORM_MAP = {
    "薄膜衣片": "片剂", "糖衣片": "片剂", "肠溶片": "片剂（肠溶）",
    "分散片": "片剂（分散）", "缓释片": "片剂（缓释）", "硬胶囊": "胶囊剂",
    "软胶囊": "胶囊剂", "注射用无菌粉末": "注射剂", "注射液": "注射液",
}


def clean_name(raw):
    """产品名称 → 通用名（去剂型后缀，保留「注射用」等前缀，与目录名一致）。"""
    name = strip_class_markers(raw)
    return strip_dosage_form(name).strip()


def clean_form(raw):
    form = re.sub(r"[\s\u3000]+", "", norm_roman(to_half_width(raw or "")))
    return FORM_MAP.get(form, form)


def norm_approval(text):
    if not text:
        return ""
    return re.sub(r"[\s\u3000]+", "",
                  norm_roman(to_half_width(str(text)))).upper()


def load_rows(path):
    rows = xlsx_lite.read_rows(path, 0)
    header_at = None
    for idx, row in enumerate(rows[:30]):
        if row and row[0].strip() == "序号" and any("批准文号" in c for c in row):
            header_at = idx
            break
    if header_at is None:
        raise SystemExit("未找到表头（序号/批准文号）")
    out = []
    for row in rows[header_at + 1:]:
        if len(row) < 10 or not any(c.strip() for c in row):
            continue
        out.append({
            "approval_number": norm_approval(row[9]),
            "product_name": row[1].strip(),
            "drug_code": row[3].strip(),
            "dosage_form": clean_form(row[5]),
            "specification": row[6].strip(),
            "manufacturer": row[8].strip(),
        })
    return out


def run(db_path, xlsx_path, dry_run=False, limit=None, report_path=None):
    db = sqlite3.connect(db_path)
    known = {norm_approval(r[0]) for r in db.execute(
        "SELECT approval_number FROM drug_registration "
        "WHERE approval_number IS NOT NULL AND approval_number<>''")}
    mol_by_key = {}
    for mid, name in db.execute(
            "SELECT molecule_id, generic_name FROM drug_molecule"):
        key = molecule_key(name)
        if key:
            mol_by_key.setdefault(key, mid)

    rows = load_rows(xlsx_path)
    if limit:
        rows = rows[:limit]

    stats = {"rows": len(rows), "new_registrations": 0, "existing_skipped": 0,
             "skipped_invalid": 0, "new_molecules": 0, "new_products": 0,
             "multi_spec_approvals": 0, "conflict_skipped": 0}
    seen = {}
    for rec in rows:
        approval = rec["approval_number"]
        generic = clean_name(rec["product_name"])
        if not approval or not generic:
            stats["skipped_invalid"] += 1
            continue
        if approval in known:
            stats["existing_skipped"] += 1
            continue
        if approval in seen:
            # 同一文号多规格：保留首个规格为代表
            if rec["specification"] and rec["specification"] != seen[approval]["specification"]:
                seen[approval]["spec_count"] += 1
            continue
        rec["generic_name"] = generic
        rec["spec_count"] = 1
        seen[approval] = rec

    for approval, rec in seen.items():
        if rec["spec_count"] > 1:
            stats["multi_spec_approvals"] += 1
        key = molecule_key(rec["generic_name"])
        mid = mol_by_key.get(key)
        if mid is None:
            if not dry_run:
                cur = db.execute(
                    "INSERT OR IGNORE INTO drug_molecule "
                    "(generic_name, is_verified, created_at, updated_at) "
                    "VALUES (?, 0, datetime('now','localtime'), "
                    "datetime('now','localtime'))", (key or rec["generic_name"],))
                mid = cur.lastrowid if cur.rowcount else db.execute(
                    "SELECT molecule_id FROM drug_molecule WHERE generic_name=?",
                    (key or rec["generic_name"],)).fetchone()[0]
            mol_by_key[key] = mid
            stats["new_molecules"] += 1
        if dry_run:
            stats["new_products"] += 1
            stats["new_registrations"] += 1
            continue
        extra = json.dumps({"drug_code": rec["drug_code"],
                            "spec_count": rec["spec_count"],
                            "registry_source": SOURCE_NOTE},
                           ensure_ascii=False)
        cur = db.execute("""
            INSERT INTO drug_product
                (molecule_id, generic_name, dosage_form, specification,
                 manufacturer_norm, trade_name, source_url, extra_data,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,
                    datetime('now','localtime'), datetime('now','localtime'))
            ON CONFLICT(generic_name, dosage_form, specification,
                        manufacturer_norm) DO NOTHING
        """, (mid, rec["generic_name"], rec["dosage_form"],
              rec["specification"], rec["manufacturer"], "", SOURCE_URL, extra))
        if cur.rowcount:
            stats["new_products"] += 1
            pid = cur.lastrowid
        else:
            row = db.execute(
                "SELECT product_id FROM drug_product WHERE generic_name=? AND "
                "dosage_form=? AND specification=? AND manufacturer_norm=?",
                (rec["generic_name"], rec["dosage_form"], rec["specification"],
                 rec["manufacturer"])).fetchone()
            pid = row[0] if row else None
        if pid is None:
            stats["conflict_skipped"] += 1
            continue
        cur = db.execute("""
            INSERT INTO drug_registration
                (product_id, approval_number, status, source_url)
            VALUES (?,?,?,?)
            ON CONFLICT(approval_number) DO NOTHING
        """, (pid, approval, "有效", SOURCE_URL))
        if cur.rowcount:
            stats["new_registrations"] += 1
        known.add(approval)

    if not dry_run:
        db.commit()
        stats["db_molecules"] = db.execute(
            "SELECT COUNT(*) FROM drug_molecule").fetchone()[0]
        stats["db_products"] = db.execute(
            "SELECT COUNT(*) FROM drug_product").fetchone()[0]
        stats["db_registrations"] = db.execute(
            "SELECT COUNT(*) FROM drug_registration").fetchone()[0]
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)),
                    exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats}, fh, ensure_ascii=False, indent=2)
    db.close()
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="品种充盈（官方公开表 → registry）")
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--source", default="hunan")
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--report", default="logs/registry_import_report.json")
    args = ap.parse_args(argv)
    stats = run(args.db, args.xlsx, dry_run=args.dry_run, limit=args.limit,
                report_path=args.report)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("IMPORT_REGISTRY_OK" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
