# -*- coding: utf-8 -*-
"""Probe CDE chemical-drug catalog page to locate the real leaflet (说明书) entry.

CDE recently migrated directory pages; the legacy /hymz/index path returns 404.
This probe opens the catalog page referenced from CDE's official help page and
records: post-challenge URL, visible anchors/buttons, and any XHR/fetch calls
made while the page loads (so the collector can call the same JSON API).
"""
import json
import re
import sys
import time
from urllib.parse import urljoin

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
sys.path.insert(0, ROOT)

CATALOG_URL = "https://www.cde.org.cn/hymlj/listpage/9cd8db3b7530c6fa0c86485e563f93c7"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    from playwright.sync_api import sync_playwright

    captured = []

    def on_response(resp):
        url = resp.url
        if "cde.org.cn" not in url:
            return
        try:
            ctype = resp.headers.get("content-type", "")
        except Exception:
            ctype = ""
        entry = {
            "url": url,
            "status": resp.status,
            "method": resp.request.method,
            "post_data": None,
            "ctype": ctype,
        }
        if resp.request.method in ("POST", "PUT"):
            try:
                entry["post_data"] = resp.request.post_data
            except Exception:
                pass
        captured.append(entry)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1440, "height": 960})
        page = ctx.new_page()
        page.on("response", on_response)
        print("OPEN", CATALOG_URL)
        page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=60000)
        # CDE JS challenge usually resolves within a few seconds; give it room.
        for _ in range(6):
            time.sleep(2)
            title = page.title()
            if title and "jsjiami" not in title.lower():
                break
        time.sleep(2)
        print("FINAL_URL", page.url)
        print("TITLE", page.title())
        print("HTML_LEN", len(page.content()))

        text = page.inner_text("body")
        print("BODY_TEXT_LEN", len(text))
        print("BODY_TEXT_HEAD", text[:800].replace("\n", " | "))

        # Enumerate anchors and buttons that mention 说明书/目录/药品/查询
        nodes = page.eval_on_selector_all(
            "a,button,.btn,input[type=button]",
            """els => els.map(e => ({
                tag: e.tagName,
                text: (e.innerText||e.value||'').trim().slice(0,60),
                href: e.href||e.getAttribute('data-href')||'',
                cls: (e.className||'').toString().slice(0,80)
            })).filter(x => x.text || x.href)""",
        )
        print("NODES", json.dumps(nodes[:120], ensure_ascii=False))

        kw = [n for n in nodes if any(k in (n["text"] + n["href"]) for k in
                                      ("说明书", "目录集", "上市", "查询", "详细信息"))]
        print("KEY_NODES", json.dumps(kw, ensure_ascii=False))

        print("NET", json.dumps(captured[-40:], ensure_ascii=False, indent=1))

        # Save a page snapshot for offline selector work
        html = page.content()
        out = sys.argv[2] if len(sys.argv) > 2 else "cde_catalog_probe.html"
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print("SAVED", out)
        browser.close()


if __name__ == "__main__":
    main()
