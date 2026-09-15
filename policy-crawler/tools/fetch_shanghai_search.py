# -*- coding: utf-8 -*-
"""上海市医保局站内检索（渲染式）：按关键词取公开文件条目。

合规：每关键词间隔 ≥4 秒；不登录、不提交表单；仅读取公开检索结果。
用法：python tools/fetch_shanghai_search.py 双通道 谈判药品 "挂网价格"
输出：logs/sh_search_results.json
"""
import io
import json
import sys
import time
import urllib.parse

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

DEFAULT_KEYWORDS = ("双通道", "谈判药品", "挂网价格", "定点零售药店")
SEARCH = "https://ybj.sh.gov.cn/websearch/index.html#search/query="


def main():
    keywords = sys.argv[1:] or list(DEFAULT_KEYWORDS)
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()
        for idx, kw in enumerate(keywords):
            if idx:
                time.sleep(4)
            url = SEARCH + urllib.parse.quote(kw)
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(6000)
                items = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('a').forEach(a => {
                        const t = (a.innerText || '').trim();
                        const h = a.href || '';
                        if (t.length > 6 && h && h.indexOf('javascript') !== 0
                            && !/^https?:\\/\\/ybj\\.sh\\.gov\\.cn\\/websearch/.test(h))
                            out.push({text: t, href: h});
                    });
                    return out;
                }""")
                total = page.evaluate(
                    "() => document.body.innerText.match(/约?\\s*\\d+\\s*条/)?.[0] || ''")
                out[kw] = {"count_hint": total, "items": items[:80]}
                print("==", kw, "items", len(items), "hint", total)
                for it in items[:12]:
                    print("   ", it["text"][:70].replace("\n", " "),
                          "->", it["href"][:110])
            except Exception as exc:
                out[kw] = {"error": "{}: {}".format(type(exc).__name__,
                                                    str(exc)[:120])}
                print("ERR", kw, type(exc).__name__, str(exc)[:100])
        ctx.close()
        browser.close()
    with open("logs/sh_search_results.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("SH_SEARCH_FETCH_DONE")


if __name__ == "__main__":
    main()
