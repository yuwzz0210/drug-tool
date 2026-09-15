# -*- coding: utf-8 -*-
"""One-time helper: log in to yp.eliancloud.cn in a visible browser yourself,
then save the session cookies to a local JSON file for the crawler.

Usage:
    python tools/elian_login_save_cookies.py --out logs/elian_cookies.json

The browser window opens on the member login page. Log in with your own
account, then press Enter in this console. Cookies are written to --out.
No credentials are stored in code, logs, or the output file (cookie values are
session tokens only).
"""
import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LOGIN_URL = "https://yp.eliancloud.cn/Member/Home/Index"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="logs/elian_cookies.json")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
        print("请在打开的浏览器中登录会员账号；登录完成后回到本窗口按回车…")
        input()
        page.wait_for_timeout(2000)
        cookies = ctx.cookies()
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(cookies, fh, ensure_ascii=False, indent=1)
        print("cookies saved:", args.out, "| count:", len(cookies))
        browser.close()


if __name__ == "__main__":
    main()
