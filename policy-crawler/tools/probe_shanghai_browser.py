# -*- coding: utf-8 -*-
"""用真实浏览器（Playwright/Chromium）访问上海阳光医药采购网，破解纯 HTTP 403。

合规：单次访问、浏览间隔 ≥4 秒、不登录、不提交表单；仅读取公开页面。
输出：logs/sh_probe.json

用法：python tools/probe_shanghai_browser.py
"""
import io
import json
import re
import sys
import time

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

PAGES = (
    "https://www.smpaa.cn/",
)
KEYWORDS = ("双通道", "挂网", "价格", "公示", "通知", "药品")


def main():
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="zh-CN",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"))
        page = ctx.new_page()
        for idx, url in enumerate(PAGES):
            if idx:
                time.sleep(4)
            try:
                resp = page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                title = page.title()
                html = page.content()
                links = []
                for a in page.query_selector_all("a"):
                    try:
                        text = (a.inner_text() or "").strip()
                        href = a.get_attribute("href") or ""
                    except Exception:
                        continue
                    if text and any(k in text for k in KEYWORDS):
                        links.append({"text": text[:80], "href": href[:160]})
                out[url] = {"status": resp.status if resp else None,
                            "title": title, "bytes": len(html),
                            "links": links[:60]}
                print(url, resp.status if resp else "-", title,
                      "links", len(links))
            except Exception as exc:
                out[url] = {"error": "{}: {}".format(type(exc).__name__,
                                                     str(exc)[:120])}
                print("ERR", url, type(exc).__name__, str(exc)[:120])
        ctx.close()
        browser.close()
    with open("logs/sh_probe.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("SH_PROBE_DONE -> logs/sh_probe.json")


if __name__ == "__main__":
    main()
