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
    keywords = []
    page = 1
    while True:
        total, rows = drugs.fetch_products(page=page, size=100)
        for r in rows:
            kw = _keyword_from_generic(r["generic_name"])
            if kw and kw not in keywords:
                keywords.append(kw)
        if page * 100 >= total:
            break
        page += 1
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
    parser.add_argument("--retries", type=int, default=2, help="单个关键词失败重试次数")
    parser.add_argument("--delay", type=float, default=5.0, help="关键词之间间隔秒数")
    parser.add_argument("--restart-every", type=int, default=10, help="每 N 个关键词重启浏览器，避免被限流")
    args = parser.parse_args(argv)

    drugs = DrugStore.from_path(args.db)
    if args.keywords:
        keywords = args.keywords
    else:
        keywords = load_keywords(drugs, limit=args.limit)
    print("待回填关键词数:", len(keywords), keywords[:20])

    report = {"keywords": len(keywords), "ok": 0, "failed": [], "new_records": 0,
              "new_products": 0, "new_registrations": 0, "retries": 0, "elapsed": 0.0}
    start = time.time()
    seen = set()
    collector = None
    since_restart = 0
    try:
        for idx, kw in enumerate(keywords, 1):
            last_err = None
            for attempt in range(args.retries + 1):
                t0 = time.time()
                try:
                    if collector is None or since_restart >= args.restart_every:
                        if collector:
                            collector.close()
                        collector = NmpaBrowserCollector(headless=not args.headed)
                        since_restart = 0
                        time.sleep(3)
                    since_restart += 1
                    collector.search(kw, max_pages=args.max_pages, details=args.details,
                                     wait_challenge=12 if since_restart == 1 else 0)
                    records = parse_captured(collector.captured)
                    collector.captured = []
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
                          % (idx, len(keywords), kw, len(fresh), time.time() - t0), flush=True)
                    break
                except Exception as exc:
                    last_err = str(exc)[:200]
                    report["retries"] += 1
                    print("[%d/%d] %s 第%d次失败: %s" % (idx, len(keywords), kw, attempt + 1, last_err[:140]), flush=True)
                    if collector:
                        try:
                            collector.close()
                        except Exception:
                            pass
                        collector = None
                        since_restart = args.restart_every  # 强制下次重启
                    time.sleep(6)
            if last_err is not None and report["ok"] < idx:
                report["failed"].append({"keyword": kw, "error": last_err})
            time.sleep(args.delay)
    finally:
        if collector:
            collector.close()
        drugs.close()
    report["elapsed"] = round(time.time() - start, 1)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
