# -*- coding: utf-8 -*-
"""探测新数据源可达性：上市药品目录集（NMPA/CDE）与湖南招采网。

只读探测：打印状态码、标题、页面大小，用于判断后续能否批量采集。
用法：python tools/probe_new_sources.py
"""
import io
import re
import ssl
import sys
import urllib.error
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

URLS = (
    "https://www.nmpa.gov.cn/datasearch/home-index.html",
    "https://www.cde.org.cn/main/xxgk/listpage9f9c74c73e0f8f56a8bfbc646055026d",
    "https://www.cde.org.cn/",
    "https://cn.bing.com/search?q=%E4%B8%8A%E5%B8%82%E8%8D%AF%E5%93%81%E7%9B%AE%E5%BD%95%E9%9B%86+%E5%AE%98%E6%96%B9",
    "https://tps.ybj.hunan.gov.cn/tps-local/",
    "https://tps.ybj.hunan.gov.cn/",
)


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=25, context=CTX) as resp:
        raw = resp.read(200000)
        return resp.status, raw


def main():
    for url in URLS:
        try:
            status, raw = fetch(url)
        except urllib.error.HTTPError as exc:
            print("%-70s HTTP %s" % (url[:70], exc.code))
            continue
        except Exception as exc:
            print("%-70s ERR %s" % (url[:70], type(exc).__name__))
            continue
        body = raw.decode("utf-8", "replace")
        title = re.search(r"<title>(.*?)</title>", body, re.S)
        print("%-70s %s %6dKB | %s" % (
            url[:70], status, len(raw) // 1024,
            (title.group(1).strip()[:40] if title else "")))
        if "bing.com" in url:
            hits = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                              body, re.S)
            shown = 0
            for href, text in hits:
                label = re.sub(r"<[^>]+>", "", text).strip()
                if not label or shown >= 8:
                    continue
                if any(k in label for k in ("目录集", "药品", "药监", "CDE")):
                    print("     ->", label[:50], href[:90])
                    shown += 1
    print("PROBE_NEW_SOURCES_DONE")


if __name__ == "__main__":
    main()
