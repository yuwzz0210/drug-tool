# -*- coding: utf-8 -*-
"""After passing the datasearch challenge, call the official dataCenter API
from inside the page context (same-origin) to learn dataset totals/columns."""
import io
import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HOME = "https://www.nmpa.gov.cn/datasearch/home-index.html"


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        c = b.new_context(user_agent=UA, locale="zh-CN",
                          viewport={"width": 1440, "height": 960})
        p = c.new_page()
        p.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        time.sleep(12)
        js = """async (body) => {
          const r = await fetch('/datasearch/dataCenter', {
            method: 'POST',
            headers: {'Content-Type': 'application/json',
                      'X-Requested-With': 'XMLHttpRequest'},
            body: JSON.stringify(body)
          });
          return await r.json();
        }"""
        for tval in ("1", "2"):
            try:
                res = p.evaluate(js, {
                    "page": 1, "pageSize": 5,
                    "conditions": [{"field": "type", "value": tval}],
                    "keyword": "",
                })
                d = res.get("data") or {}
                print("TYPE", tval, "total", d.get("total"))
                lst = d.get("list") or []
                print("  rows", len(lst))
                if lst:
                    print("  keys", sorted(lst[0].keys()))
                    print("  row0", json.dumps(lst[0], ensure_ascii=False)[:400])
            except Exception as exc:
                print("TYPE", tval, "ERR", repr(exc)[:160])
        b.close()


if __name__ == "__main__":
    main()
