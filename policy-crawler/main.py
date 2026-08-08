# -*- coding: utf-8 -*-
"""CLI 入口：crawl / check-robots / init-db / cron。

示例：
    python main.py init-db
    python main.py crawl --source nmpa --demo          # 离线演示（使用测试夹具）
    python main.py crawl --source nmpa --days 7        # 线上抓取（默认遵守合规延迟）
    python main.py crawl --source nmpa --dry-run --no-delay   # 试跑不写库
    python main.py crawl --source nmpa --file <本地html>       # 离线解析真实页面（调试选择器）
    python main.py crawl --source nmpa --days 1 --output data/policies.json  # 输出站点 JSON
    python main.py check-robots --url https://www.nmpa.gov.cn/xxgk/fgwj/gzwj/gzwjyp/
    python main.py cron
"""
import argparse
import datetime
import json
import os
import sys
import uuid
from urllib.parse import urlparse

from compliance import RobotsChecker
from config import DB_PATH, SMTP_HOST, SOURCES, load_all_sources
from downloader import Downloader, PauseSignal
from logging_conf import setup_logger
from models import Policy
from parsers import PARSERS
from pipeline import Pipeline
from scheduler import daily_commands
from store import PostgresStore, SqliteStore


log = setup_logger()


def _alert(message):
    """403/验证码等反爬信号：日志告警；配置 SMTP_HOST 后可扩展邮件通知。"""
    log.error("ALERT %s", message)
    if SMTP_HOST:
        log.info("邮件告警通道已配置 SMTP_HOST=%s（实现见 roadmap）", SMTP_HOST)


def build_store(db_path, use_postgres=False):
    if use_postgres:
        return PostgresStore(os.environ.get("DB_URL"))
    return SqliteStore(db_path)


def cmd_init_db(args):
    store = build_store(args.db, args.postgres)
    log.info("数据库初始化完成 db=%s", args.db if not args.postgres else os.environ.get("DB_URL"))
    store.close() if hasattr(store, "close") else None


def _recent(item, days):
    if days <= 0 or not item.get("date"):
        return True
    try:
        d = datetime.datetime.strptime(item["date"], "%Y-%m-%d").date()
    except ValueError:
        return True
    return (datetime.date.today() - d).days <= days


def _load_json_records(filepath):
    """读取已存在的 JSON 数组；文件缺失或损坏时返回空列表。"""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        log.warning("JSON 输出文件无法解析，将覆盖重建: %s", filepath)
        return []


def save_to_json(policies, filepath):
    """抓取结果合并去重后写入 JSON 数组文件，供静态网站直接读取。

    每条记录字段：id（按 url 稳定生成）、title、url、publish_date、
    content_preview（正文前 200 字）、source_site、created_at。
    增量更新：读取已存在的文件，按 url 去重合并（新数据覆盖旧数据），
    输出按 publish_date 倒序排列；本次无数据时不改写文件。
    """
    records = _load_json_records(filepath)
    by_url = {r.get("url"): r for r in records if r.get("url")}
    now = datetime.datetime.now().isoformat(timespec="seconds")
    added = 0
    for policy in policies:
        url = (getattr(policy, "source_url", "") or "").strip()
        if not url:
            continue
        old = by_url.get(url)
        record = {
            "id": (old or {}).get("id") or "p_" + uuid.uuid4().hex[:12],
            "title": (getattr(policy, "title", "") or "").strip(),
            "url": url,
            "publish_date": (getattr(policy, "publish_date", "") or "").strip(),
            "content_preview": (getattr(policy, "content", "") or "")[:200],
            "source_site": (getattr(policy, "issuing_authority", "") or "").strip(),
            "created_at": now,
        }
        if url not in by_url:
            added += 1
        by_url[url] = record
    if not by_url:
        log.info("本次无有效数据，保留原文件 %s", filepath)
        return []
    ordered = sorted(by_url.values(), key=lambda r: r.get("publish_date") or "", reverse=True)
    os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
    log.info("JSON 输出 %s 条（新增 %s）→ %s", len(ordered), added, filepath)
    return ordered


def cmd_crawl(args):
    all_sources = load_all_sources()
    source = all_sources.get(args.source)
    if not source:
        log.error("未知数据源：%s（可选 %s）", args.source, ", ".join(all_sources))
        return 1
    parser = PARSERS[source["parser"]]
    downloader = Downloader(
        delay_range=(0, 0) if args.no_delay else None,
        retries=0 if args.no_delay else None,
    )
    store = None if args.dry_run else build_store(args.db, args.postgres)
    pipeline = Pipeline(store, task_name="{}_policy".format(args.source)) if store else None

    if args.file:
        return _file_mode(source, parser, args)

    if args.demo:
        return _demo_crawl(parser, pipeline, args)

    checker = RobotsChecker()
    list_url = source["list_url"]
    if not checker.allowed(list_url):
        log.error("robots.txt 禁止抓取 %s，任务终止（合规基线）", list_url)
        return 1
    try:
        _, list_html = downloader.fetch(list_url)
    except PauseSignal:
        _alert("列表页触发反爬信号，任务暂停: {}".format(list_url))
        return 1
    keep_paths = source.get("keep_paths") or [urlparse(list_url).path]
    items = parser.parse_list(list_html, source["base"], keep_paths=keep_paths)
    items = [it for it in items if _recent(it, args.days)]
    log.info("列表解析完成：共 %s 条（最近 %s 天）", len(items), args.days if args.days > 0 else "全部")

    policies = []
    errors = 0
    for idx, item in enumerate(items[: args.limit], 1):
        try:
            _, detail_html = downloader.fetch(item["url"])
            detail = parser.parse_detail(detail_html, item["url"])
            p = Policy(
                title=detail.get("title") or item["title"],
                source_url=item["url"],
                doc_number=detail.get("doc_number", ""),
                issuing_authority=detail.get("issuing_authority") or source["name"],
                publish_date=detail.get("publish_date") or item.get("date", ""),
                implement_date=detail.get("implement_date", ""),
                content=detail.get("content", ""),
                raw_html=detail.get("raw_html", ""),
            )
            policies.append(p)
        except PauseSignal:
            _alert("详情页触发反爬信号，任务暂停: {}".format(item["url"]))
            return 1
        except Exception as exc:
            errors += 1
            log.exception("详情解析失败 %s", item["url"])
        if args.dry_run and idx % 5 == 0:
            log.info("dry-run 已解析 %s/%s 条", idx, min(len(items), args.limit))
    log.info("详情解析完成：%s 条成功，%s 条失败", len(policies), errors)
    output = args.output or "data/policies.json"
    if policies:
        try:
            save_to_json(policies, output)
        except Exception as exc:
            log.error("JSON 输出失败（不影响抓取流程）: %s", exc)
    if args.dry_run:
        log.info("dry-run 模式不写库，解析到 %s 条政策", len(policies))
        return 0
    result = pipeline.process(policies)
    log.info("抓取任务完成 status=%s new=%s/%s", result["status"], result["new_added"], result["total"])
    return 0


def _file_mode(source, parser, args):
    """离线调试：读取本地 HTML 作为列表页，打印解析结果，不联网不写库。"""
    with open(args.file, encoding="utf-8", errors="replace") as f:
        html = f.read()
    keep_paths = source.get("keep_paths") or [urlparse(source["list_url"]).path]
    items = parser.parse_list(html, source["base"], keep_paths=keep_paths)
    log.info("[file] 列表解析 %s 条（来源 %s）", len(items), source["name"])
    for it in items:
        print("{date}\t{title}\t{url}".format(date=it.get("date", ""), title=it["title"], url=it["url"]))
    if not items:
        print("解析结果为 0 条：请提供该列表页原始 HTML，以便按真实结构调整选择器。")
    return 0


def _demo_crawl(parser, pipeline, args):
    """离线演示：使用 tests/fixtures 完整跑通 列表→详情→脱敏→入库。"""
    import glob

    base = os.path.dirname(os.path.abspath(__file__))
    fixtures = os.path.join(base, "tests", "fixtures")
    list_file = os.path.join(fixtures, "nmpa_list.html")
    with open(list_file, encoding="utf-8") as f:
        list_html = f.read()
    nmpa = SOURCES["nmpa"]
    items = parser.parse_list(
        list_html, nmpa["base"],
        keep_paths=nmpa.get("keep_paths") or [urlparse(nmpa["list_url"]).path],
    )
    log.info("[demo] 列表解析 %s 条", len(items))
    detail_file = os.path.join(fixtures, "nmpa_detail.html")
    with open(detail_file, encoding="utf-8") as f:
        detail_html = f.read()
    policies = []
    for item in items:
        detail = parser.parse_detail(detail_html, item["url"])
        policies.append(Policy(
            title=detail.get("title") or item["title"],
            source_url=item["url"],
            doc_number=detail.get("doc_number", ""),
            issuing_authority=detail.get("issuing_authority") or SOURCES["nmpa"]["name"],
            publish_date=detail.get("publish_date") or item.get("date", ""),
            content=detail.get("content", ""),
            raw_html=detail.get("raw_html", ""),
        ))
    if getattr(args, "output", None):
        save_to_json(policies, args.output)
    if args.dry_run or pipeline is None:
        log.info("[demo] dry-run：解析 %s 条，未写库", len(policies))
        return 0
    result = pipeline.process(policies)
    log.info("[demo] 入库完成 status=%s new=%s", result["status"], result["new_added"])
    return 0


def cmd_check_robots(args):
    checker = RobotsChecker()
    ok = checker.allowed(args.url)
    log.info("robots 检查：%s -> %s", args.url, "允许" if ok else "禁止")
    return 0 if ok else 1


def cmd_cron(args):
    for line in daily_commands(args.dir or os.getcwd(), args.python):
        print(line)
    return 0


def cmd_serve(args):
    from serve import serve

    store = build_store(args.db, args.postgres)
    httpd = serve(store, host=args.host, port=args.port)
    log.info("API 服务启动 http://%s:%s（Ctrl+C 退出）", args.host, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="医药流通政策信息聚合平台 - 爬虫")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-db", help="初始化数据库")
    p_init.add_argument("--db", default=DB_PATH)
    p_init.add_argument("--postgres", action="store_true", help="使用 PostgreSQL（需 DB_URL）")
    p_init.set_defaults(func=cmd_init_db)

    p_crawl = sub.add_parser("crawl", help="抓取政策")
    p_crawl.add_argument("--source", default="nmpa")
    p_crawl.add_argument("--days", type=int, default=7, help="仅抓最近 N 天（0=全部）")
    p_crawl.add_argument("--limit", type=int, default=50, help="单次最多抓取条数")
    p_crawl.add_argument("--db", default=DB_PATH)
    p_crawl.add_argument("--postgres", action="store_true")
    p_crawl.add_argument("--dry-run", action="store_true", help="只解析不写库")
    p_crawl.add_argument("--no-delay", action="store_true", help="关闭合规延迟（仅测试）")
    p_crawl.add_argument("--demo", action="store_true", help="离线演示（使用测试夹具）")
    p_crawl.add_argument("--file", default="", help="读取本地 HTML 作为列表页（离线调试选择器）")
    p_crawl.add_argument("--output", default=None, help="输出 JSON 文件路径（默认 data/policies.json）")
    p_crawl.set_defaults(func=cmd_crawl)

    p_robots = sub.add_parser("check-robots", help="检查 robots.txt 权限")
    p_robots.add_argument("--url", required=True)
    p_robots.set_defaults(func=cmd_check_robots)

    p_cron = sub.add_parser("cron", help="生成每日定时任务 crontab")
    p_cron.add_argument("--dir", default="")
    p_cron.add_argument("--python", default=sys.executable)
    p_cron.set_defaults(func=cmd_cron)

    p_serve = sub.add_parser("serve", help="启动零依赖 REST API")
    p_serve.add_argument("--db", default=DB_PATH)
    p_serve.add_argument("--postgres", action="store_true")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
