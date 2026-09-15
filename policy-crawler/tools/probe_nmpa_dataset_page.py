# -*- coding: utf-8 -*-
"""Click the 境内生产药品 dataset entry and inspect whether a full-list page
loads without a keyword."""
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
    bodies = []

    def on_resp(resp):
        if "dataCenter" in resp.url:
            try:
                bodies.append((resp.url, resp.json()))
            except Exception:
                pass

    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        c = b.new_context(user_agent=UA, locale="zh-CN",
                          viewport={"width": 1440, "height": 960})
        p = c.new_page()
        p.on("response", on_resp)
        p.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        time.sleep(12)
        # exact dataset anchors
        for txt in ("境内生产药品", "境外生产药品"):
            try:
                p.get_by_text(txt, exact=True).first.click(timeout=4000)
                time.sleep(4)
                print("clicked", txt, "pages", len(c.pages))
            except Exception as exc:
                print("click fail", txt, repr(exc)[:90])
        time.sleep(4)
        for pg in c.pages:
            print("URL", pg.url[:170])
        print("BODIES", len(bodies))
        for url, js in bodies[:4]:
            d = js.get("data") or {}
            print("total", d.get("total"), "rows", len(d.get("list") or []))
            lst = d.get("list") or []
            if lst:
                print("keys", sorted(lst[0].keys()))
                print("row0", json.dumps(lst[0], ensure_ascii=False)[:400])
        b.close()


if __name__ == "__main__":
    main()
