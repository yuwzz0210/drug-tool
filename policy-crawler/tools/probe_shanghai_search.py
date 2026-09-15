# -*- coding: utf-8 -*-
"""通过上海市医保局站内检索定位「双通道 / 挂网价」公开文件（只读探测）。

做法：真实浏览器打开首页 → 找到搜索框 → 提交关键词 → 记录结果页 URL、
条目与网络请求，便于后续写成正式采集器。请求间隔 ≥4 秒，不登录。

用法：python tools/probe_shanghai_search.py [关键词]
输出：logs/sh_search_probe.json
"""
import io
import json
import sys
import time

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

HOME = "https://ybj.sh.gov.cn/"
KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "双通道"


def main():
    from playwright.sync_api import sync_playwright
    out = {"keyword": KEYWORD, "steps": []}
    reqs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()
        page.on("request", lambda r: reqs.append(r.url[:180]))
        page.goto(HOME, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        boxes = page.eval_on_selector_all(
            "input", "els => els.map(e => [e.type, e.id, e.name, e.placeholder])")
        out["inputs"] = boxes
        print("inputs:", boxes)

        target = None
        for sel in ("input#searchContent:visible",
                    "input[placeholder*='搜索']:visible",
                    "input[placeholder*='关键字']:visible",
                    "input[type=text]:visible"):
            loc = page.locator(sel)
            if loc.count():
                target = loc.first
                print("using selector", sel, "count", loc.count())
                break
        if target is None:
            out["note"] = "未找到搜索框"
        else:
            target.click()
            target.fill(KEYWORD)
            page.keyboard.press("Enter")
            page.wait_for_timeout(6000)
            out["after_url"] = page.url
            out["after_title"] = page.title()
            items = page.eval_on_selector_all(
                "a", "els => els.map(e => [e.innerText, e.href])")
            out["result_links"] = [
                {"text": (t or "").strip()[:100], "href": h}
                for t, h in items if t and t.strip()][:60]
            print("after:", page.url, "links", len(items))
            for it in out["result_links"][:15]:
                print("   ", it["text"][:70], "->", it["href"][:110])
        time.sleep(4)
        ctx.close()
        browser.close()
    out["requests"] = sorted(set(reqs))[-40:]
    with open("logs/sh_search_probe.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("SH_SEARCH_PROBE_DONE")


if __name__ == "__main__":
    main()
