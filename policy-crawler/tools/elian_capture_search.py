# -*- coding: utf-8 -*-
"""Semi-manual capture: open the DomesticList page, you click 搜索 and then
下一页 once, this script records the XHRs so we can replicate the real API.

Run, then in the opened browser: 1) click 搜索, 2) click 下一页 once,
3) return here and press Enter. Output: logs/elian_xhr_dump.json
"""
import io
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

URL = ("https://yp.eliancloud.cn/Member/DataQuery/DomesticList"
       "?ChannelID=e759afea-713a-4439-8cf4-0ffad89578a3")


def main():
    hits = []

    def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            body = None
            if "json" in ct or resp.url.endswith((".ashx", ".do", ".action")):
                try:
                    body = resp.text()[:1500]
                except Exception:
                    body = None
            hits.append({
                "url": resp.url[:260],
                "status": resp.status,
                "method": resp.request.method,
                "post": resp.request.post_data[:500]
                if resp.request.post_data else None,
                "ct": ct,
                "body": body,
            })
        except Exception:
            pass

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=False)
        c = b.new_context(locale="zh-CN",
                          viewport={"width": 1600, "height": 1000})
        c.add_cookies(json.load(open(r"logs/elian_cookies.json",
                                     encoding="utf-8")))
        p = c.new_page()
        p.on("response", on_response)
        p.goto(URL, wait_until="domcontentloaded", timeout=90000)
        for f in p.frames:
            f.on("response", on_response)
        time.sleep(4)
        print("请在打开的窗口里：1) 点一次【搜索】 2) 点一次【下一页】；完成后按回车…")
        input()
        time.sleep(2)
        os.makedirs("logs", exist_ok=True)
        with open("logs/elian_xhr_dump.json", "w", encoding="utf-8") as fh:
            json.dump(hits, fh, ensure_ascii=False, indent=1)
        print("captured", len(hits), "-> logs/elian_xhr_dump.json")
        denied = [h for h in hits if "ExceptionPage" in h["url"]]
        if denied:
            print("权限异常：检测到", len(denied),
                  "次 ExceptionPage（用户无访问权限）——请重新登录后再试，"
                  "或确认账号已开通该模块")
        b.close()


if __name__ == "__main__":
    main()
