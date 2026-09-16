# -*- coding: utf-8 -*-
"""Wave-1 前端校验：确认「国谈 / 双通道 / 湖南挂网价 / 上海支付标准 / 病种」已上线。

做法：进程内起本地静态服务 → Playwright 打开页面 → 等待快照加载 →
打开指定品种详情 → 断言关键字段与来源链接存在。

用法：python tools/qa_wave1_frontend.py [品种名]
"""
import functools
import http.server
import io
import os
import socketserver
import sys
import threading

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

def _find_site():
    """向上查找包含 repo/index.html 的目录（兼容不同检出位置）。"""
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        cand = os.path.join(cur, "repo")
        if os.path.exists(os.path.join(cand, "index.html")):
            return cand
        cur = os.path.dirname(cur)
    return os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "repo")


SITE = _find_site()
PORT = 8791
TARGET = sys.argv[1] if len(sys.argv) > 1 else "吡咯替尼"

CHECKS = (
    "双通道：",
    "国家谈判",
    "挂网价（湖南·官方）",
    "医保支付标准（上海·官方）",
    "价格历史时间线",
)


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                               directory=SITE)
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    httpd.serve_forever()


def main():
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        logs = []
        page.on("console", lambda m: logs.append(m.text))
        page.goto("http://127.0.0.1:%d/index.html" % PORT,
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        hydrated = any("官方药品数据同步完成" in t for t in logs)
        results.append(("快照加载", hydrated))
        page.evaluate("(n)=>{ if(typeof openDrugDetail==='function') openDrugDetail(n); }",
                      TARGET)
        page.wait_for_timeout(1500)
        body = page.inner_text("body")
        for needle in CHECKS:
            results.append((needle, needle in body))
        html = page.content()
        results.append(("原始文件链接",
                        "ybj.hunan.gov.cn" in html or "ybj.sh.gov.cn" in html))
        browser.close()
    ok = all(flag for _, flag in results)
    for name, flag in results:
        print(("PASS  " if flag else "FAIL  ") + name)
    print("QA_WAVE1_FRONTEND_" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
