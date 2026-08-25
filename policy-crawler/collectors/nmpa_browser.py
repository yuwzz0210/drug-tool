# -*- coding: utf-8 -*-
"""NMPA 数据查询全自动采集器（Playwright 驱动）。

原理：NMPA 数据查询带 JS 反爬 + 接口签名（sign/timestamp）。用真实浏览器自动通过挑战，
并驱动页面自身的请求层（签名由页面自动计算），采集官方接口 JSON。

流程：
    首页搜索框输入关键词 → 自动弹出结果窗口 → 翻页采集列表 → 点击详情采集完整字段。

用法：
    python -m collectors.nmpa_browser --keyword 阿托伐他汀 --db policy_crawler.db \
        --out ../work/nmpa_captured --max-pages 3 --details 5

合规：仅读取公开数据；逐页请求由页面自身频率控制；不绕过任何鉴权。
"""
import argparse
import json
import logging
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.nmpa_drugs import import_registrations  # noqa: E402
from drugstore import DrugStore  # noqa: E402


log = logging.getLogger("policy-crawler.collectors.nmpa_browser")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HOME_URL = "https://www.nmpa.gov.cn/datasearch/home-index.html"

DETAIL_FIELDS = {
    "f0": "approval_number", "f1": "generic_name", "f3": "trade_name",
    "f4": "dosage_form", "f5": "specification", "f6": "holder",
    "f8": "manufacturer", "f9": "approval_date", "f11": "drug_type",
    "f12": "origin_approval", "f13": "drug_code",
}


def _kill_intro(page):
    page.evaluate("""
      () => {
        document.querySelectorAll('.introjs-overlay,.introjs-helperLayer,.introjs-tooltip,.introjs-arrow')
          .forEach(el => el.remove());
        if (window.introJs) { try { window.introJs().exit(); } catch (e) {} }
      }
    """)


class NmpaBrowserCollector:
    def __init__(self, headless=True):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=headless, args=["--disable-blink-features=AutomationControlled"])
        self._ctx = self._browser.new_context(
            user_agent=UA, locale="zh-CN", viewport={"width": 1440, "height": 960})
        self.captured = []  # [{kind, url, body}]
        self._ctx.on("page", lambda pg: pg.on("response", self._on_response))

    def _on_response(self, resp):
        url = resp.url
        if "/datasearch/data/nmpadata/search" in url or "/datasearch/data/nmpadata/queryDetail" in url:
            try:
                body = json.loads(resp.text())
            except Exception:
                return
            kind = "detail" if "queryDetail" in url else "list"
            self.captured.append({"kind": kind, "url": url, "body": body})
            log.info("捕获 %s 响应: %s", kind, url[:150])

    def search(self, keyword, max_pages=20, details=0, wait_challenge=12):
        page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        page.goto(HOME_URL, timeout=60000)
        page.wait_for_timeout(wait_challenge * 1000)
        _kill_intro(page)
        box = None
        for el in page.locator("input").all():
            ph = el.get_attribute("placeholder") or ""
            if el.is_visible() and "请选择" not in ph:
                box = el
                break
        if box is None:
            raise RuntimeError("未找到首页搜索框")
        box.fill(keyword)
        page.wait_for_timeout(1500)
        box.press("Enter")
        page.wait_for_timeout(2500)
        try:
            page.locator("button:visible").first.click()
        except Exception:
            pass
        page.wait_for_timeout(3000)
        # 等待结果窗口出现
        result_page = None
        deadline = time.time() + 30
        while time.time() < deadline:
            for pg in self._ctx.pages:
                if "search-result" in pg.url:
                    result_page = pg
                    break
            if result_page is None and self.captured and any(
                    c["kind"] == "list" for c in self.captured):
                # 列表已捕获但未匹配到窗口 URL，取最后一个页面
                result_page = self._ctx.pages[-1]
            if result_page:
                break
            time.sleep(1)
        if result_page is None:
            raise RuntimeError("未出现搜索结果窗口")
        result_page.wait_for_timeout(6000)
        _kill_intro(result_page)
        # 翻页
        for _ in range(max_pages - 1):
            try:
                nxt = result_page.locator("button:has-text('下一页')").first
                if not nxt.is_visible():
                    break
                nxt.click()
                result_page.wait_for_timeout(2500)
            except Exception:
                break
        # 抓详情
        if details > 0:
            try:
                links = result_page.locator("a:has-text('详情'), button:has-text('详情')")
                n = min(details, links.count())
                for i in range(n):
                    try:
                        links.nth(i).click()
                        result_page.wait_for_timeout(2000)
                        # 详情可能在弹窗/新窗口，关闭返回
                        for pg in list(self._ctx.pages):
                            if pg is not result_page and "search-result" not in pg.url:
                                pg.close()
                        try:
                            result_page.keyboard.press("Escape")
                        except Exception:
                            pass
                    except Exception:
                        continue
            except Exception as exc:
                log.warning("详情抓取异常: %s", exc)
        return result_page

    def save(self, out_dir, keyword):
        os.makedirs(out_dir, exist_ok=True)
        safe = keyword.replace("/", "_")
        path = os.path.join(out_dir, "nmpa_%s.json" % safe)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"keyword": keyword, "captured": self.captured},
                      f, ensure_ascii=False, indent=2)
        return path

    def close(self):
        try:
            self._browser.close()
        finally:
            self._pw.stop()


def parse_captured(captured):
    """把采集到的 list/detail 响应归一化为注册记录（详情优先、按文号去重）。"""
    records = {}
    for item in captured:
        body = item.get("body") or {}
        if body.get("code") != 200:
            continue
        data = body.get("data") or {}
        rows = data.get("list") if item["kind"] == "list" else [data]
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if item["kind"] == "list":
                rec = {
                    "approval_number": row.get("f0", ""),
                    "generic_name": row.get("f1", ""),
                    "manufacturer": row.get("f2", ""),
                    "drug_code": row.get("f3", ""),
                }
            else:
                rec = {}
                for alias, field in DETAIL_FIELDS.items():
                    rec[field] = row.get(alias, "")
                if not rec.get("generic_name"):
                    rec["generic_name"] = row.get("f1", "")
            if not rec.get("approval_number") or not rec.get("generic_name"):
                continue
            old = records.get(rec["approval_number"]) or {}
            old.update({k: v for k, v in rec.items() if v})
            records[rec["approval_number"]] = old
    return list(records.values())


def main(argv=None):
    parser = argparse.ArgumentParser(description="NMPA 数据查询全自动采集器")
    parser.add_argument("--keyword", required=True, action="append", help="查询关键词（可多次）")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--out", default=os.path.join(ROOT, "work", "nmpa_captured"))
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--details", type=int, default=5)
    parser.add_argument("--no-import", action="store_true", help="只采集不写库")
    parser.add_argument("--headed", action="store_true", help="有头模式（调试）")
    args = parser.parse_args(argv)

    collector = NmpaBrowserCollector(headless=not args.headed)
    all_records = {}
    try:
        for keyword in args.keyword:
            collector.search(keyword, max_pages=args.max_pages, details=args.details)
            path = collector.save(args.out, keyword)
            print("已保存捕获文件:", path)
            for rec in parse_captured(collector.captured):
                all_records[rec["approval_number"]] = rec
            collector.captured = []
    finally:
        collector.close()
    records = list(all_records.values())
    print("解析到注册记录:", len(records))
    for r in records[:5]:
        print(" ", r["approval_number"], r["generic_name"], r.get("dosage_form", ""),
              r.get("specification", ""), r.get("manufacturer", ""))
    if records and not args.no_import:
        drugs = DrugStore.from_path(args.db)
        report = import_registrations(drugs, records)
        drugs.close()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
