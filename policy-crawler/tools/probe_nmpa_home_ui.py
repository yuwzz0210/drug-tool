# -*- coding: utf-8 -*-
"""Probe NMPA datasearch home: find the 国产药品 entry & result table shape."""
import io
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        c = b.new_context(user_agent=UA, locale="zh-CN",
                          viewport={"width": 1440, "height": 960})
        p = c.new_page()
        p.goto("https://www.nmpa.gov.cn/datasearch/home-index.html",
               wait_until="domcontentloaded", timeout=60000)
        time.sleep(12)
        nodes = p.eval_on_selector_all(
            "a,button,li,div",
            """els => els.map(e => ({
                tag: e.tagName,
                text: (e.innerText||'').trim().slice(0,40),
                cls: (e.className||'').toString().slice(0,60)
              })).filter(x => x.text)""")
        kw = [n for n in nodes if any(k in n["text"] for k in
                                      ("国产药品", "进口药品", "查询", "药品"))]
        print("KEY_NODES")
        for n in kw[:24]:
            print(n)
        # try clicking a node whose text contains 国产药品
        clicked = False
        for n in kw:
            if "国产药品" in n["text"]:
                try:
                    p.get_by_text(n["text"], exact=False).first.click(timeout=3000)
                    clicked = True
                    break
                except Exception as exc:
                    print("click fail", exc)
        time.sleep(5)
        print("PAGES", len(c.pages))
        for pg in c.pages:
            print("URL", pg.url[:120])
        result = c.pages[-1] if len(c.pages) > 1 else p
        try:
            heads = result.eval_on_selector_all(
                "th .cell, thead th",
                "els => els.map(e => (e.innerText||'').trim())")
            print("HEADERS", heads)
            rows = result.eval_on_selector_all(
                ".el-table__body tbody tr",
                """els => els.slice(0,3).map(tr =>
                    [...tr.querySelectorAll('td')].map(td =>
                        (td.innerText||'').trim()))""")
            print("ROWS", rows)
        except Exception as exc:
            print("table err", repr(exc)[:120])
        b.close()


if __name__ == "__main__":
    main()
