# -*- coding: utf-8 -*-
"""批量回填：把药库现有品种的官方注册信息从 NMPA 自动补全入库。

用法（policy-crawler 目录下）：
    python tools/backfill_nmpa.py --db policy_crawler.db --limit 5
    python tools/backfill_nmpa.py --db policy_crawler.db --keywords 奥希替尼 吉非替尼

流程：读取药库通用名 → 归一化关键词 → NMPA 浏览器采集器逐个抓取 →
      解析官方响应 → 幂等入库（批准文号唯一键）。
"""
import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.nmpa_browser import NmpaBrowserCollector, parse_captured  # noqa: E402
from collectors.nmpa_drugs import import_registrations  # noqa: E402
from drugstore import DrugStore  # noqa: E402


FORM_SUFFIXES = (
    "片", "胶囊", "软胶囊", "注射液", "注射剂", "颗粒", "口服液", "口服溶液",
    "滴眼液", "栓剂", "气雾剂", "散剂", "丸", "丸剂", "糖浆", "干混悬剂",
    "喷雾剂", "凝胶剂", "乳膏剂", "软膏剂", "贴膏剂", "贴剂", "混悬剂",
    "溶液剂", "滴剂", "洗剂", "搽剂", "膜剂", "植入剂",
)


def _keyword_from_generic(gn):
    """通用名 → 检索关键词：去掉括号注记与剂型后缀。"""
    name = (gn or "").strip()
    base = re.split(r"[（(]", name)[0].strip()
    for suffix in FORM_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base


def load_keywords(drugs, limit=0):
    _, rows = drugs.fetch_products(page=1, size=100000)
    keywords = []
    for r in rows:
        kw = _keyword_from_generic(r["generic_name"])
        if kw and kw not in keywords:
            keywords.append(kw)
    if limit:
        keywords = keywords[:limit]
    return keywords


def main(argv=None):
    parser = argparse.ArgumentParser(description="NMPA 官方数据批量回填")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--keywords", nargs="*", default=None, help="指定关键词（缺省从药库读取）")
    parser.add_argument("--limit", type=int, default=0, help="最多回填前 N 个关键词")
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--details", type=int, default=2)
    parser.add_argument("--out", default=os.path.join(ROOT, "work", "nmpa_captured"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    drugs = DrugStore.from_path(args.db)
    if args.keywords:
        keywords = args.keywords
    else:
        keywords = load_keywords(drugs, limit=args.limit)
    print("待回填关键词数:", len(keywords), keywords[:20])

    collector = NmpaBrowserCollector(headless=not args.headed)
    report = {"keywords": len(keywords), "ok": 0, "failed": [], "new_records": 0,
              "new_products": 0, "new_registrations": 0, "elapsed": 0.0}
    start = time.time()
    seen = set()
    try:
        for idx, kw in enumerate(keywords, 1):
            t0 = time.time()
            try:
                collector.search(kw, max_pages=args.max_pages, details=args.details,
                                 wait_challenge=12 if idx == 1 else 0)
                records = parse_captured(collector.captured)
                collector.captured = []
                # 按批准文号去重（跨关键词）
                fresh = [r for r in records if r.get("approval_number") not in seen]
                for r in fresh:
                    seen.add(r["approval_number"])
                if fresh:
                    imp = import_registrations(drugs, fresh)
                    report["new_records"] += len(fresh)
                    report["new_products"] += imp["products"]
                    report["new_registrations"] += imp["registrations"]
                report["ok"] += 1
                print("[%d/%d] %s → %d 条新记录 (%.1fs)"
                      % (idx, len(keywords), kw, len(fresh), time.time() - t0))
            except Exception as exc:
                report["failed"].append({"keyword": kw, "error": str(exc)[:200]})
                print("[%d/%d] %s 失败: %s" % (idx, len(keywords), kw, str(exc)[:150]))
    finally:
        collector.close()
        drugs.close()
    report["elapsed"] = round(time.time() - start, 1)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
