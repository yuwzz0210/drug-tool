# -*- coding: utf-8 -*-
"""列出上海市医保局政策文件栏目条目，定位「双通道 / 谈判药品 / 挂网价」文件。

用法：python tools/probe_shanghai_list.py [max_pages]
输出：logs/sh_list.json
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
BASE = "https://ybj.sh.gov.cn/zcwj/"
KEYWORDS = ("双通道", "谈判药品", "挂网", "价格", "定点零售药店", "医保药品目录")


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
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    all_items = []
    pages = {}
    for idx in range(max_pages):
        url = BASE + ("index.html" if idx == 0 else "index_%d.html" % idx)
        if idx:
            time.sleep(4)
        try:
            st, body = fetch(url)
        except Exception as exc:
            pages[url] = "ERR %s" % type(exc).__name__
            continue
        items = []
        for m in re.finditer(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>",
                             body, re.S | re.I):
            label = re.sub(r"<[^>]+>", "", m.group(2))
            label = re.sub(r"\s+", " ", label).strip()
            href = m.group(1)
            if len(label) < 8 or not re.search(r"\d{4}|\d{2}/\d{2}", href):
                continue
            items.append({"text": label[:90],
                          "url": urllib.parse.urljoin(url, href),
                          "hit": any(k in label for k in KEYWORDS)})
        pages[url] = {"status": st, "items": len(items),
                      "hits": sum(1 for i in items if i["hit"])}
        all_items.extend(items)
        print(url, st, "items", len(items),
              "hits", pages[url]["hits"])

    seen = set()
    uniq = []
    for it in all_items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        uniq.append(it)
    with open("logs/sh_list.json", "w", encoding="utf-8") as fh:
        json.dump({"pages": pages, "items": uniq}, fh,
                  ensure_ascii=False, indent=2)
    print("--- keyword hits")
    for it in uniq:
        if it["hit"]:
            print(it["text"][:70], "->", it["url"][:110])
    print("SH_LIST_DONE total", len(uniq))


if __name__ == "__main__":
    main()
