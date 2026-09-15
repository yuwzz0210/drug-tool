# -*- coding: utf-8 -*-
"""Dump the real pagination structure of the elian DomesticList data frame."""
import io
import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

URL = ("https://yp.eliancloud.cn/Member/DataQuery/DomesticList"
       "?ChannelID=e759afea-713a-4439-8cf4-0ffad89578a3")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        c = b.new_context(user_agent=UA, locale="zh-CN",
                          viewport={"width": 1600, "height": 1000})
        c.add_cookies(json.load(open(r"logs/elian_cookies.json",
                                     encoding="utf-8")))
        p = c.new_page()
        p.goto(URL, wait_until="domcontentloaded", timeout=90000)
        time.sleep(8)
        f = None
        for fr in p.frames:
            if "/Member/DataQuery/DomesticList" in fr.url.split("?")[0]:
                f = fr
                break
        print("frame", f.url if f else None)
        if not f:
            b.close()
            return
        info = f.evaluate("""() => {
          const body = document.body.innerText || '';
          const idx = body.indexOf('共');
          const pager = [];
          document.querySelectorAll('a,button,li,span').forEach(e => {
            const t = (e.innerText||'').trim();
            if (/^\\d+$/.test(t) || /下一页|下页|末页|尾页|>/.test(t)) {
              pager.push({tag:e.tagName, text:t.slice(0,12),
                cls:(e.className||'').toString().slice(0,80),
                html:(e.outerHTML||'').slice(0,220)});
            }
          });
          return {around: body.slice(Math.max(0,idx-120), idx+220),
                  pager: pager.slice(0,40)};
        }""")
        print("AROUND", info["around"].replace("\n", " | "))
        for x in info["pager"][:30]:
            print(x)
        b.close()


if __name__ == "__main__":
    main()
