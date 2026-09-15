# -*- coding: utf-8 -*-
"""Replicate the datasearch user flow with an empty keyword to reach the full
domestic dataset; dump totals, row keys, and result-table headers."""
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
        if "dataCenter" in resp.url and resp.request.method == "POST":
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
        box = None
        for el in p.locator("input").all():
            try:
                ph = el.get_attribute("placeholder") or ""
                if el.is_visible() and "请选择" not in ph:
                    box = el
                    break
            except Exception:
                continue
        print("box found", box is not None)
        if box:
            box.fill("")
            box.press("Enter")
            time.sleep(2)
            try:
                p.locator("button:visible").first.click(timeout=3000)
            except Exception as exc:
                print("click", repr(exc)[:80])
        time.sleep(8)
        print("PAGES", len(c.pages))
        for pg in c.pages:
            print("URL", pg.url[:160])
        print("BODIES", len(bodies))
        for url, js in bodies[:3]:
            d = js.get("data") or {}
            print("TOTAL", d.get("total"))
            lst = d.get("list") or []
            print("ROWS", len(lst))
            if lst:
                print("KEYS", sorted(lst[0].keys()))
                print("ROW0", json.dumps(lst[0], ensure_ascii=False)[:500])
        result = c.pages[-1] if len(c.pages) > 1 else p
        for sel in (".el-table__header-wrapper th", ".el-table th",
                    "thead th", "table thead th"):
            try:
                heads = result.eval_on_selector_all(
                    sel, "els => els.map(e => (e.innerText||'').trim())")
                if heads:
                    print("HEADS via", sel, heads[:20])
                    break
            except Exception:
                continue
        try:
            rows = result.eval_on_selector_all(
                ".el-table__body-wrapper tbody tr, .el-table__body tbody tr",
                """els => els.slice(0,3).map(tr =>
                    [...tr.querySelectorAll('td')].map(td =>
                        (td.innerText||'').trim().slice(0,30)))""")
            print("ROWS_DOM", rows)
        except Exception as exc:
            print("rows err", repr(exc)[:100])
        b.close()


if __name__ == "__main__":
    main()
