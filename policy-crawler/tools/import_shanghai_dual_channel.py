# -*- coding: utf-8 -*-
"""上海「双通道」药品名单 → dual_channel（region=上海）。

数据来源（官方公开）：沪医保医管发〔2021〕40 号《关于落实国家医保谈判
药品"双通道"管理机制的通知》附件「上海市纳入"双通道"管理的药品名单」，
2021-11-27 发布、2021-12-01 执行，共 96 个药品（附件表：序号/药品名称/剂型）。
页面：http://ybj.sh.gov.cn/qtwj/20211130/b4e8016fe52145e384b81159cce7fd13.html

口径说明：名单为上海首批"双通道"药品；市医保部门按国家目录调整适时更新，
因此 batch 标记为「首批2021」，notes 保留原始文件信息，便于后续替换新名单。
分子/品种按名称回挂，回挂不上仍保留名单本体（可追溯）。

用法：
    python tools/import_shanghai_dual_channel.py --db policy_crawler.db \
        --pdf logs/regional/4071d1129606b6775649edf23b48f433.pdf --dry-run
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

SOURCE_URL = ("http://ybj.sh.gov.cn/qtwj/20211130/"
              "b4e8016fe52145e384b81159cce7fd13.html")
BATCH = "首批2021"
REGION = "上海"
EFFECTIVE = "2021-12-01"
NOTES = ("沪医保医管发〔2021〕40号 附件：上海市纳入“双通道”管理的药品名单"
         "（2021-11-27发布，2021-12-01执行）")

FORM_PATTERN = (
    r"注射剂|口服常释剂型|颗粒剂|乳膏剂|缓释控释剂型|缓释注射剂|"
    r"吸入气雾剂|吸入粉雾剂|雾化吸入溶液|粉雾剂|滴眼剂|灌肠剂|脂质体注射剂"
)
ROW_RE = re.compile(
    r"^(?P<no>\d{1,3})\s+(?P<name>.+?)\s*(?P<form>(?:" + FORM_PATTERN
    + r").*)?$")


def parse_rows(pdf_path):
    """解析附件表格，返回 [(药品名称, 剂型), ...]。"""
    import pdfplumber
    items = []
    started = False
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "双通道" in text and "药品名单" in text:
                started = True
            if not started:
                continue
            for line in text.splitlines():
                line = re.sub(r"[ \t]+", " ", line).strip()
                if not line or line.startswith("序号") or line.startswith("-"):
                    continue
                if "附件" in line or "药品名单" in line:
                    continue
                m = ROW_RE.match(line)
                if not m:
                    continue
                name = (m.group("name") or "").strip()
                form = (m.group("form") or "").strip()
                if not name:
                    continue
                items.append((name, form))
    # 去重（同药名同剂型只保留一条；如地舒单抗两个规格会保留剂型差异信息）
    seen = set()
    out = []
    for name, form in items:
        key = (name, form)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, form))
    return out


def run(db_path, pdf_path, dry_run=False, report_path=None, reset=False):
    db = sqlite3.connect(db_path)
    mol_index = build_index(db.execute(
        "SELECT molecule_id, generic_name FROM drug_molecule").fetchall())
    rows = parse_rows(pdf_path)
    stats = {"parsed": len(rows), "stored": 0, "molecule_linked": 0}
    if reset and not dry_run:
        # 仅显式 --reset 时清理本地区本批次数据；默认只做幂等 upsert
        db.execute("DELETE FROM dual_channel WHERE region=? AND batch=?",
                   (REGION, BATCH))
    for name, form in rows:
        mol_id, _how = pick_molecule(name, mol_index)
        if mol_id:
            stats["molecule_linked"] += 1
        stats["stored"] += 1
        if not dry_run:
            db.execute("""
                INSERT INTO dual_channel
                    (molecule_id, product_id, region, drug_name, dosage_form,
                     specification, status, effective_date, batch, source_url,
                     notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(region, drug_name, dosage_form, specification)
                DO UPDATE SET
                    molecule_id=excluded.molecule_id,
                    effective_date=excluded.effective_date,
                    batch=excluded.batch, source_url=excluded.source_url,
                    notes=excluded.notes
            """, (mol_id, None, REGION, name, form, "", "纳入", EFFECTIVE,
                  BATCH, SOURCE_URL, NOTES))
    if not dry_run:
        db.commit()
    stats["dual_channel_total"] = db.execute(
        "SELECT COUNT(*) FROM dual_channel").fetchone()[0]
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)),
                    exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats,
                       "rows": [{"name": n, "form": f} for n, f in rows]},
                      fh, ensure_ascii=False, indent=2)
    db.close()
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="上海双通道名单导入")
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="先清理本地区本批次旧数据再写入（默认只 upsert）")
    ap.add_argument("--report", default="logs/sh_dual_channel_report.json")
    args = ap.parse_args(argv)
    stats = run(args.db, args.pdf, dry_run=args.dry_run,
                report_path=args.report, reset=args.reset)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("IMPORT_SH_DUAL_OK" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
