# -*- coding: utf-8 -*-
"""Open any CDE page in a real browser, survive the JS challenge, and dump:
page text, anchors/buttons, JSON network bodies (so we can see real payloads).

Usage:
    python tools/probe_cde_page.py <url> [out_prefix]
"""
import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://www.cde.org.cn/hymlj/listpage/9cd8db3b7530c6fa0c86485e563f93c7")
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "cde_page"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    from playwright.sync_api import sync_playwright

    nets = []

    def on_response(resp):
        url = resp.url
        if "cde.org.cn" not in url:
            return
        ctype = ""
        try:
            ctype = resp.headers.get("content-type", "")
        except Exception:
            pass
        is_json = "json" in ctype or "/hymlj/" in url or "/main/" in url
        body = None
        if is_json and resp.status == 200:
            try:
                body = resp.text()[:20000]
            except Exception:
                pass
        nets.append({
            "url": url,
            "status": resp.status,
            "method": resp.request.method,
            "post": None if resp.request.method != "POST" else resp.request.post_data,
            "ctype": ctype,
            "body": body,
        })

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1440, "height": 960})
        page = ctx.new_page()
        page.on("response", on_response)
        print("OPEN", URL)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(6):
            time.sleep(2)
            if page.title() and "jsjiami" not in page.title().lower():
                break
        time.sleep(3)
        print("FINAL_URL", page.url)
        print("TITLE", page.title())
        text = page.inner_text("body")
        print("BODY_TEXT_LEN", len(text))
        print("BODY_TEXT_HEAD", text[:5000].replace("\n", " | "))

        nodes = page.eval_on_selector_all(
            "a,button,input[type=button]",
            """els => els.map(e => ({
                tag: e.tagName,
                text: (e.innerText||e.value||'').trim().slice(0,80),
                href: e.href||e.getAttribute('data-href')||'',
                cls: (e.className||'').toString().slice(0,100)
            })).filter(x => x.text || x.href)""",
        )
        print("NODES", json.dumps(nodes[:160], ensure_ascii=False))

        kw = [n for n in nodes if any(k in (n["text"] + n["href"]) for k in
                                      ("说明书", "适应症", "用法", "不良反应", "详情",
                                       "查询", "PDF", "下载", "下一页"))]
        print("KEY_NODES", json.dumps(kw, ensure_ascii=False))

        html = page.content()
        with open(PREFIX + ".html", "w", encoding="utf-8") as fh:
            fh.write(html)
        with open(PREFIX + "_net.json", "w", encoding="utf-8") as fh:
            json.dump(nets, fh, ensure_ascii=False, indent=1)
        print("SAVED", PREFIX + ".html", PREFIX + "_net.json")
        print("NET_COUNT", len(nets))
        browser.close()


if __name__ == "__main__":
    main()
