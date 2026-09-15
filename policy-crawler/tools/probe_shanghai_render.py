# -*- coding: utf-8 -*-
"""用渲染式浏览器读取上海市医保局栏目（列表页为 JS 渲染），找双通道/挂网价文件。

用法：python tools/probe_shanghai_render.py
输出：logs/sh_render.json
"""
import io
import json
import sys
import time

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

PAGES = (
    "https://ybj.sh.gov.cn/zcwj/",
    "https://ybj.sh.gov.cn/",
)
KEYWORDS = ("双通道", "谈判药品", "挂网", "价格公示", "药品价格", "定点零售")


def main():
    from playwright.sync_api import sync_playwright
    out = {}
    xhr = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()

        def on_response(resp):
            url = resp.url
            if any(k in url for k in (".json", "search", "list", "query")):
                xhr.append(url[:160])

        page.on("response", on_response)
        for idx, url in enumerate(PAGES):
            if idx:
                time.sleep(4)
            try:
                resp = page.goto(url, timeout=45000,
                                 wait_until="networkidle")
                page.wait_for_timeout(2000)
                items = page.eval_on_selector_all(
                    "a", "els => els.map(e => [e.innerText, e.href])")
                hits = [{"text": (t or "").strip()[:90], "href": h}
                        for t, h in items
                        if any(k in (t or "") for k in KEYWORDS)]
                out[url] = {"status": resp.status if resp else None,
                            "title": page.title(),
                            "links": len(items), "hits": hits[:40]}
                print(url, "links", len(items), "hits", len(hits))
                for h in hits[:15]:
                    print("   ", h["text"], "->", h["href"][:100])
            except Exception as exc:
                out[url] = {"error": "{}: {}".format(type(exc).__name__,
                                                     str(exc)[:120])}
                print("ERR", url, type(exc).__name__, str(exc)[:110])
        ctx.close()
        browser.close()
    out["_xhr"] = sorted(set(xhr))[:40]
    with open("logs/sh_render.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("SH_RENDER_DONE")


if __name__ == "__main__":
    main()
