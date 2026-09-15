# -*- coding: utf-8 -*-
"""上海执行的国家医保谈判药品「医保支付标准」→ price_history。

数据来源（官方公开）：上海市医保局《关于执行〈国家基本医疗保险、生育保险和
工伤保险药品目录〉以及〈商业健康保险创新药品目录〉（2025年）的通知》
（2026-01-04）附件 PDF 的「协议期内谈判药品部分」表格，含
药品名称 / 医保支付标准 / 备注（支付限定）/ 协议有效期 / 支付比例。
页面：http://ybj.sh.gov.cn/qtwj/20260104/3d5b634c0163425aad9dabd9d3efae52.html

口径说明（避免与挂网价混淆）：
- price_type 固定为「医保支付标准」，region=上海，batch=2025目录；
- 仅导入官方公布的具体金额条目；目录中标注「*」（未公布具体金额）的条目不写值；
- 支付标准是分子（通用名+剂型）层级，按 drug_product 回挂后逐品种落库，
  notes 保留协议期与支付限定原文，便于回溯；
- 未回挂到本库分子/品种的条目计入审计样本（不影响名单本身）。

用法：
    python tools/import_shanghai_payment_standard.py --db policy_crawler.db \
        --pdf logs/regional/aaf2ae7d166f3c2bc6da66ee98a55f23.pdf --dry-run
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

from molecule_match import build_index, pick_molecule  # noqa: E402

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

SOURCE_URL = ("http://ybj.sh.gov.cn/qtwj/20260104/"
              "3d5b634c0163425aad9dabd9d3efae52.html")
BATCH = "2025目录"
REGION = "上海"
PRICE_TYPE = "医保支付标准"
CATALOG = "国家基本医疗保险、生育保险和工伤保险药品目录（2025年）（上海执行）"

STANDARD_RE = re.compile(r"^([\d.]+)\s*元")
PERIOD_RE = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")


def parse_period(text):
    m = PERIOD_RE.search(text or "")
    if not m:
        return "", ""
    start = "%04d-%02d-%02d" % tuple(int(x) for x in m.groups())
    rest = PERIOD_RE.findall(text)[1:]
    if rest:
        end = "%04d-%02d-%02d" % tuple(int(x) for x in rest[0])
    else:
        end = ""
    return start, end


def parse_negotiation_rows(pdf_path):
    """解析「协议期内谈判药品部分」表格，返回 [{name, standard, unit, ...}]。"""
    import pdfplumber
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
        # 目录页也会出现章节名，需以「含表头的正文页」作为起点
        start = None
        for idx, text in enumerate(pages):
            if ("协议期内谈判药品部分" in text
                    and "医保支付标准" in text):
                start = idx
                break
        if start is None:
            return rows
        end = len(pages)
        for idx in range(start + 1, len(pages)):
            if "中药饮片部分" in pages[idx]:
                end = idx
                break
        for page in pdf.pages[start:end]:
            table = page.extract_table()
            if not table:
                continue
            for row in table:
                cells = [(c or "").replace("\n", " ").strip() for c in row]
                if len(cells) < 12:
                    continue
                category = cells[5]
                name = cells[7]
                standard = cells[8]
                remark = cells[9]
                period = cells[10]
                pay = cells[11]
                if category not in ("甲", "乙") or not name:
                    continue
                m = STANDARD_RE.match(standard)
                price = float(m.group(1)) if m else None
                unit = ""
                if m:
                    unit = re.sub(r"^[\d.]+\s*元[（(]?", "", standard)
                    unit = unit.rstrip("）)")
                    unit = re.sub(r"\s*[（(]\s*$", "", unit).strip()
                rows.append({
                    "name": re.sub(r"\s+", "", name),
                    "category": category,
                    "standard_raw": standard,
                    "price": price,
                    "unit": unit,
                    "remark": remark,
                    "period": period,
                    "pay_ratio": pay,
                })
    return rows


def run(db_path, pdf_path, dry_run=False, report_path=None, reset=False):
    db = sqlite3.connect(db_path)
    mol_index = build_index(db.execute(
        "SELECT molecule_id, generic_name FROM drug_molecule").fetchall())
    products = {}
    for pid, mid in db.execute(
            "SELECT product_id, molecule_id FROM drug_product "
            "WHERE molecule_id IS NOT NULL"):
        products.setdefault(mid, []).append(pid)

    entries = parse_negotiation_rows(pdf_path)
    stats = {"entries": len(entries), "with_price": 0, "star_no_price": 0,
             "molecule_linked": 0, "match_exact": 0, "match_longest_stem": 0,
             "products_written": 0, "unmatched": 0}
    unmatched = []
    if reset and not dry_run:
        db.execute("DELETE FROM price_history WHERE region=? AND batch=?",
                   (REGION, BATCH))
    for e in entries:
        if e["price"] is None:
            stats["star_no_price"] += 1
            continue
        stats["with_price"] += 1
        mid, how = pick_molecule(e["name"], mol_index)
        if not mid:
            stats["unmatched"] += 1
            if len(unmatched) < 50:
                unmatched.append({"name": e["name"],
                                  "standard": e["standard_raw"]})
            continue
        stats["molecule_linked"] += 1
        if how == "exact":
            stats["match_exact"] += 1
        elif how == "longest-stem":
            stats["match_longest_stem"] += 1
        start, end = parse_period(e["period"])
        note = "%s；协议期=%s" % (CATALOG, e["period"].strip())
        if e["remark"]:
            note += "；支付限定=" + re.sub(r"\s+", "", e["remark"])[:120]
        if not dry_run:
            for pid in products.get(mid, []):
                stats["products_written"] += 1
                db.execute("""
                    INSERT INTO price_history
                        (product_id, price_type, price, unit, region, batch,
                         price_flag, effective_date, expire_date, source_url,
                         notes)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(product_id, price_type, region, batch,
                                effective_date) DO UPDATE SET
                        price=excluded.price, unit=excluded.unit,
                        expire_date=excluded.expire_date,
                        source_url=excluded.source_url, notes=excluded.notes
                """, (pid, PRICE_TYPE, e["price"], e["unit"] or "",
                      REGION, BATCH, e["category"], start, end, SOURCE_URL,
                      note))
        else:
            stats["products_written"] += len(products.get(mid, []))
    if not dry_run:
        db.commit()
    stats["price_history_total"] = db.execute(
        "SELECT COUNT(*) FROM price_history").fetchone()[0]
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)),
                    exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats, "unmatched_sample": unmatched},
                      fh, ensure_ascii=False, indent=2)
    db.close()
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="上海医保支付标准导入")
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--report", default="logs/sh_payment_report.json")
    args = ap.parse_args(argv)
    stats = run(args.db, args.pdf, dry_run=args.dry_run,
                report_path=args.report, reset=args.reset)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("IMPORT_SH_PAYMENT_OK" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
