# -*- coding: utf-8 -*-
"""湖南官方价格公示表 → price_history（挂网价）+ dual_channel（双通道标识）。

数据来源（官方公开附件，湖南省医疗保障局）：
《2026年二季度湖南省药品价格信息公布表》
http://ybj.hunan.gov.cn/ybj/first113541/firstF/info1/202608/t20260806_34040891.html
附件列：序号/产品名称/商品名/药品统一编码/药品类型/剂型/规格/包装/生产企业/
批准文号(注册证编号)/药品质量层次/医保报销种类/是否集采中选药品/是否双通道药品/
是否国家谈判药品/是否价格保密/最小包装医保平台挂网价/最小制剂价格

导入口径（不猜测、不补值）：
- 价格：仅当批准文号能在 drug_registration 命中时才写 price_history
  （product_id 必须真实存在）；未命中的行计入审计报告，待注册库补齐后回挂；
- 双通道：文件中「是否双通道药品=是」的行写入 dual_channel（region=湖南），
  分子/品种按名称与批准文号尽可能回挂，回挂不上仍保留名单本体（可追溯）；
- 价格保密行为空的直接跳过并计数。

用法：
    python tools/import_regional_hunan.py --db policy_crawler.db \
        --xlsx logs/regional/hunan_2026q2_price.xlsx --dry-run
    python tools/import_regional_hunan.py --db policy_crawler.db \
        --xlsx logs/regional/hunan_2026q2_price.xlsx
"""
import argparse
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
from molecule_match import (  # noqa: E402
    build_index as build_molecule_index,
    pick_molecule,
)
from normalize import norm_roman, to_half_width  # noqa: E402

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

SOURCE_URL = ("http://ybj.hunan.gov.cn/ybj/first113541/firstF/info1/202608/"
              "t20260806_34040891.html")
BATCH = "2026Q2"
REGION = "湖南"
NOTES = "2026年二季度湖南省药品价格信息公布表（公布日2026-08-06）"

HEADER_MARK = "序号"
COLS = {
    "name": 1, "trade_name": 2, "code": 3, "drug_type": 4, "dosage_form": 5,
    "specification": 6, "package": 7, "manufacturer": 8,
    "approval_number": 9, "quality_level": 10, "insurance_type": 11,
    "is_vbp": 12, "is_dual": 13, "is_negotiation": 14, "is_secret": 15,
    "listed_price": 16, "unit_price": 17,
}


def norm_approval(text):
    """批准文号归一：全角→半角、去空格、罗马数字统一。"""
    if not text:
        return ""
    t = norm_roman(to_half_width(str(text)))
    return re.sub(r"[\s\u3000]+", "", t)


def parse_price(text):
    if text is None:
        return None
    t = str(text).strip().replace(",", "").replace("￥", "").replace("元", "")
    if not t or t in ("-", "/", "—"):
        return None
    try:
        value = float(t)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def load_rows(path):
    """定位表头行并返回数据行（dict 列表）。"""
    rows = xlsx_lite.read_rows(path, 0)
    header_at = None
    for idx, row in enumerate(rows[:30]):
        if row and row[0].strip() == HEADER_MARK and any(
                "批准文号" in c for c in row):
            header_at = idx
            break
    if header_at is None:
        raise SystemExit("未找到表头行（序号/批准文号）")
    out = []
    for row in rows[header_at + 1:]:
        if not any(c.strip() for c in row):
            continue
        rec = {}
        for key, idx in COLS.items():
            rec[key] = row[idx].strip() if idx < len(row) else ""
        out.append(rec)
    return out


def build_index(db):
    reg = {}
    for approval, product_id in db.execute(
            "SELECT approval_number, product_id FROM drug_registration "
            "WHERE approval_number IS NOT NULL AND approval_number<>''"):
        reg[norm_approval(approval)] = product_id
    mol = build_molecule_index(db.execute(
        "SELECT molecule_id, generic_name FROM drug_molecule").fetchall())
    prod_name = {}
    for pid, name in db.execute(
            "SELECT product_id, generic_name FROM drug_product"):
        key = norm_roman(to_half_width(name)).strip()
        if key:
            prod_name.setdefault(key, []).append(pid)
    return reg, mol, prod_name


def run(db_path, xlsx_path, dry_run=False, limit=None, report_path=None):
    db = sqlite3.connect(db_path)
    reg, mol_index, prod_index = build_index(db)
    rows = load_rows(xlsx_path)
    if limit:
        rows = rows[:limit]

    stats = {"rows": len(rows), "price_products": 0, "price_rows_used": 0,
             "price_skipped_secret": 0, "price_skipped_no_price": 0,
             "price_skipped_unmatched": 0, "price_multi_pack_products": 0,
             "dual_rows": 0, "dual_stored": 0, "dual_product_linked": 0,
             "dual_molecule_linked": 0, "negotiation_flagged": 0,
             "vbp_flagged": 0}
    unmatched_sample = []
    # product_id -> [(包装, 最小包装挂网价, 最小制剂价格), ...]
    price_buckets = {}
    dual_rows = []

    if not dry_run:
        # 幂等：同一来源批次先清后写，避免旧口径残留
        db.execute("DELETE FROM price_history WHERE region=? AND batch=?",
                   (REGION, BATCH))
        db.execute("DELETE FROM dual_channel WHERE region=? AND batch=?",
                   (REGION, BATCH))

    for rec in rows:
        approval = norm_approval(rec["approval_number"])
        product_id = reg.get(approval)
        pack = rec["package"]
        price = parse_price(rec["listed_price"])
        unit_price = parse_price(rec["unit_price"])
        if rec["is_secret"].strip() == "是":
            stats["price_skipped_secret"] += 1
        elif price is None and unit_price is None:
            stats["price_skipped_no_price"] += 1
        elif product_id is None:
            stats["price_skipped_unmatched"] += 1
            if len(unmatched_sample) < 50:
                unmatched_sample.append({"approval_number": approval,
                                         "name": rec["name"]})
        else:
            price_buckets.setdefault(product_id, []).append(
                (pack, price, unit_price, rec["quality_level"]))

        if rec["is_dual"].strip() == "是":
            stats["dual_rows"] += 1
            dual_rows.append((product_id, rec))
        if rec["is_negotiation"].strip() == "是":
            stats["negotiation_flagged"] += 1
        if rec["is_vbp"].strip() == "是":
            stats["vbp_flagged"] += 1

    # 价格落库：同品种多包装时取「最小制剂价格」（跨包装可比口径），
    # 包装数量与最小包装挂网价区间写入备注，保持可追溯。
    for product_id, packs in price_buckets.items():
        stats["price_products"] += 1
        stats["price_rows_used"] += len(packs)
        if len(packs) > 1:
            stats["price_multi_pack_products"] += 1
        unit_prices = [u for _, _, u, _ in packs if u is not None]
        pack_prices = [p for _, p, _, _ in packs if p is not None]
        if unit_prices:
            price, unit = unit_prices[0], "元/最小制剂单位"
        else:
            price, unit = pack_prices[0], "元/最小包装"
        flags = sorted({q for _, _, _, q in packs if q})
        note = NOTES + "；包装数=%d" % len(packs)
        if pack_prices:
            note += "；最小包装挂网价=%s" % "~".join(
                "%g" % v for v in (min(pack_prices), max(pack_prices)))
        if not dry_run:
            db.execute("""
                INSERT INTO price_history
                    (product_id, price_type, price, unit, region, batch,
                     price_flag, effective_date, source_url, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(product_id, price_type, region, batch,
                            effective_date) DO UPDATE SET
                    price=excluded.price, unit=excluded.unit,
                    price_flag=excluded.price_flag,
                    source_url=excluded.source_url, notes=excluded.notes
            """, (product_id, "挂网", price, unit, REGION, BATCH,
                  "/".join(flags), "", SOURCE_URL, note))

    # 双通道名单落库（回挂不上品种/分子的行同样保留，便于审计与后续回挂）
    for product_id, rec in dual_rows:
        mol_id, how = pick_molecule(rec["name"], mol_index)
        if product_id:
            stats["dual_product_linked"] += 1
        if mol_id:
            stats["dual_molecule_linked"] += 1
        stats["dual_match_" + how.replace("-", "_")] = \
            stats.get("dual_match_" + how.replace("-", "_"), 0) + 1
        stats["dual_stored"] += 1
        if not dry_run:
            db.execute("""
                INSERT INTO dual_channel
                    (molecule_id, product_id, region, drug_name,
                     dosage_form, specification, status, effective_date,
                     batch, source_url, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(region, drug_name, dosage_form, specification)
                DO UPDATE SET
                    molecule_id=excluded.molecule_id,
                    product_id=excluded.product_id,
                    batch=excluded.batch, source_url=excluded.source_url,
                    notes=excluded.notes
            """, (mol_id, product_id, REGION, rec["name"],
                  rec["dosage_form"], rec["specification"], "纳入", "",
                  BATCH, SOURCE_URL, NOTES))

    if not dry_run:
        db.commit()
    stats["price_history_total"] = db.execute(
        "SELECT COUNT(*) FROM price_history").fetchone()[0]
    stats["dual_channel_total"] = db.execute(
        "SELECT COUNT(*) FROM dual_channel").fetchone()[0]
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)),
                    exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats, "unmatched_price_sample":
                       unmatched_sample}, fh, ensure_ascii=False, indent=2)
    db.close()
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="湖南价格/双通道导入")
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--report", default="logs/hunan_import_report.json")
    args = ap.parse_args(argv)
    stats = run(args.db, args.xlsx, dry_run=args.dry_run, limit=args.limit,
                report_path=args.report)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("IMPORT_HUNAN_OK" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
