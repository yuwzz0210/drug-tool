# -*- coding: utf-8 -*-
"""Diagnose what the elian DomesticList page really renders with our cookies."""
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
        time.sleep(7)
        print("URL", p.url)
        print("TITLE", p.title())
        text = p.inner_text("body")
        print("BODY", text[:700].replace("\n", " | "))
        print("IFRAMES", len(p.frames))
        for f in p.frames:
            print(" frame", f.url[:140])
        for frame in p.frames:
            try:
                body = frame.inner_text("body")
                if body and len(body) > 40:
                    print(" frame body:", body[:400].replace("\n", " | "))
            except Exception:
                continue
        print("INPUTS", p.eval_on_selector_all(
            "input", "els => els.map(e => e.getAttribute('placeholder')||'')"))
        print("BUTTONS", p.eval_on_selector_all(
            "button", "els => els.map(e => (e.innerText||'').trim()).filter(Boolean)")[:25])
        b.close()


if __name__ == "__main__":
    main()
