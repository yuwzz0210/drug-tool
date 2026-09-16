# -*- coding: utf-8 -*-
"""打通药监局数据查询「境内生产药品」检索接口（只读探测）。

做三件事：
1) 打开数据查询首页并进入「境内生产药品」模块，记录落地 URL；
2) 捕获检索相关的 XHR/POST 请求（URL + 表单参数）；
3) 用测试批准文号发一次检索，记录响应结构与首行字段。

用法：python tools/probe_nmpa_search_api.py [批准文号]
输出：logs/nmpa_search_api.json
"""
import io
import json
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

HOME = "https://www.nmpa.gov.cn/datasearch/home-index.html"
KEY = sys.argv[1] if len(sys.argv) > 1 else "国药准字H20180023"


def main():
    from playwright.sync_api import sync_playwright
    out = {"key": KEY, "requests": [], "responses": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="zh-CN",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"))
        page = ctx.new_page()

        def on_request(req):
            url = req.url
            if "/datasearch/data/" in url or any(
                    k in url.lower() for k in ("search", "query")):
                item = {"method": req.method, "url": url[:200]}
                if req.method == "POST":
                    item["post"] = (req.post_data or "")[:300]
                out["requests"].append(item)

        def on_response(resp):
            url = resp.url
            if "/datasearch/data/" in url or any(
                    k in url.lower() for k in ("search", "query")):
                try:
                    body = resp.text()[:400]
                except Exception:
                    body = "<unreadable>"
                out["responses"].append({"url": url[:200], "status": resp.status,
                                         "body": body})

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(HOME, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # 进入「境内生产药品」模块
        try:
            with ctx.expect_page(timeout=8000) as new_page_info:
                page.get_by_text("境内生产药品", exact=True).first.click()
            module = new_page_info.value
        except Exception:
            module = page
        module.wait_for_timeout(5000)
        out["module_url"] = module.url
        print("模块 URL:", module.url[:110])
        inputs = module.eval_on_selector_all(
            "input", "els => els.slice(0,10).map(e => [e.type, e.id, e.name, e.placeholder])")
        out["module_inputs"] = inputs
        print("输入框:", inputs)

        # 找到可输入的关键字框，填入批准文号并检索
        target = None
        for sel in ("input#keyword", "input[placeholder*='批准文号']",
                    "input[placeholder*='关键字']", "input[type=text]"):
            loc = module.locator(sel)
            if loc.count():
                target = loc.first
                break
        if target is not None:
            try:
                target.fill(KEY)
                module.keyboard.press("Enter")
                module.wait_for_timeout(2500)
                for sel in ("button:has-text('搜索')", "button:has-text('查询')",
                            ".search-btn", "button[type=submit]"):
                    loc = module.locator(sel)
                    if loc.count():
                        try:
                            loc.first.click(timeout=5000)
                            print("点击检索按钮:", sel)
                            break
                        except Exception:
                            continue
                module.wait_for_timeout(7000)
            except Exception as exc:
                out["fill_error"] = str(exc)[:150]
        out["result_text"] = module.inner_text("body")[:800].replace("\n", " ")
        print("结果文本:", out["result_text"][:300])
        ctx.close()
        browser.close()

    with open("logs/nmpa_search_api.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("--- 捕获到 %d 个请求" % len(out["requests"]))
    for r in out["requests"][-8:]:
        print("   ", r["method"], r["url"][:120])
        if r.get("post"):
            print("        POST:", r["post"][:160])
    print("NMPA_SEARCH_API_PROBE_DONE")


if __name__ == "__main__":
    main()
