# -*- coding: utf-8 -*-
"""健康检查（规格书第 8 章运维）：数据库连通性 + 启用数据源可达性。

用法：
    python health_check.py              # 可读报告；全部通过返回 0
    python health_check.py --json       # 输出 JSON（便于接入监控）
    python health_check.py --db demo.db # 指定数据库
"""
import argparse
import datetime
import json
import sys
import urllib.request

from config import DB_PATH, load_all_sources
from store import SqliteStore


def check_db(db_path=DB_PATH):
    """检查数据库可连通且可查询。"""
    try:
        store = SqliteStore(db_path)
        count = len(store.query_policies({}))
        store.close() if hasattr(store, "close") else None
        return True, "数据库正常，政策 {} 条".format(count)
    except Exception as exc:
        return False, "数据库异常: {}".format(exc)


def _probe(url, timeout=10):
    """探测单个 URL：HEAD 优先，服务器拒绝时退化为 GET。"""
    ua = "policy-crawler-health-check/1.0"
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status


def check_sources(fetch=None, timeout=10):
    """逐个探测启用数据源列表页可达性；403/412 视为可达但被反爬拦截。"""
    results = []
    for key, src in load_all_sources().items():
        if not src.get("enabled"):
            continue
        url = src["list_url"]
        try:
            status = fetch(url) if fetch else _probe(url, timeout)
            if status is None:
                ok, detail = False, "无响应"
            elif status < 400:
                ok, detail = True, "HTTP {}".format(status)
            elif status in (403, 412):
                ok, detail = False, "HTTP {}（站点可达，但被反爬拦截）".format(status)
            else:
                ok, detail = False, "HTTP {}".format(status)
        except Exception as exc:
            ok, detail = False, str(exc)
        results.append({"source": key, "url": url, "ok": ok, "detail": detail})
    return results


def run(db_path=DB_PATH, fetch=None):
    db_ok, db_msg = check_db(db_path)
    sources = check_sources(fetch=fetch)
    return {
        "ok": db_ok and all(s["ok"] for s in sources),
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "db": {"ok": db_ok, "detail": db_msg},
        "sources": sources,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="爬虫系统健康检查")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    report = run(db_path=args.db)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("健康检查 {}（{}）".format("通过" if report["ok"] else "异常", report["checked_at"]))
        print("  数据库: {}".format(report["db"]["detail"]))
        for s in report["sources"]:
            print("  源 {}: {} - {}".format(s["source"], "OK" if s["ok"] else "FAIL", s["detail"]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
