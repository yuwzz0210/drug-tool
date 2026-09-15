# -*- coding: utf-8 -*-
"""探测上海市医保局站点结构：检索入口 + 双通道/挂网价相关栏目。

合规：请求间隔 ≥4 秒、浏览器 UA、只读。
输出：logs/sh_sources.json

用法：python tools/probe_shanghai_sources.py
"""
import io
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

HOME = "https://ybj.sh.gov.cn/"
CANDIDATES = (
    "https://ybj.sh.gov.cn/search/index.html?keyword=%E5%8F%8C%E9%80%9A%E9%81%93",
    "https://ybj.sh.gov.cn/zcwj/index.html",
    "https://ybj.sh.gov.cn/tzgg/index.html",
)
KEYWORDS = ("双通道", "挂网", "价格", "药品", "谈判", "定点零售")


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=25, context=CTX) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return resp.status, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return resp.status, raw.decode("utf-8", "replace")


def main():
    report = {}
    status, html = fetch(HOME)
    search_forms = sorted(set(re.findall(
        r'(?:action|href)="([^"]*search[^"]*)"', html, re.I)))
    js_hooks = sorted(set(re.findall(
        r'([A-Za-z0-9_./-]*search[A-Za-z0-9_./?=-]*)', html, re.I)))[:20]
    menus = sorted(set(re.findall(r"<a[^>]*>([^<]{2,30})</a>", html)))
    report[HOME] = {"status": status, "bytes": len(html),
                    "search_forms": search_forms[:20],
                    "js_hooks": js_hooks,
                    "menus": [m for m in menus
                              if any(k in m for k in KEYWORDS)][:40]}
    print("HOME", status, len(html))
    print("search_forms:", search_forms[:10])
    print("menus:", report[HOME]["menus"][:20])

    for url in CANDIDATES:
        time.sleep(4)
        try:
            st, body = fetch(url)
            text = re.sub(r"<[^>]+>", " ", body)
            text = re.sub(r"\s+", " ", text)
            hits = []
            for m in re.finditer(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>",
                                 body, re.S | re.I):
                label = re.sub(r"<[^>]+>", "", m.group(2))
                label = re.sub(r"\s+", " ", label).strip()
                if label and any(k in label for k in KEYWORDS):
                    hits.append({"text": label[:70],
                                 "url": urllib.parse.urljoin(url, m.group(1))})
            report[url] = {"status": st, "bytes": len(body),
                           "hits": hits[:40], "text_head": text[:200]}
            print(url, st, len(body), "hits", len(hits))
        except Exception as exc:
            report[url] = {"error": "{}: {}".format(type(exc).__name__,
                                                    str(exc)[:120])}
            print("ERR", url, type(exc).__name__, str(exc)[:100])

    with open("logs/sh_sources.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("SH_SOURCES_DONE")


if __name__ == "__main__":
    main()
