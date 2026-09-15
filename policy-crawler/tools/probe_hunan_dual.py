# -*- coding: utf-8 -*-
"""抓取湖南医保局「挂网价」文章页并列出附件；同时找出站点检索入口。

用法：python tools/probe_hunan_dual.py
输出：logs/hunan_probe.json
"""
import io
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

URLS = (
    "http://ybj.hunan.gov.cn/ybj/first113541/firstF/info1/202608/"
    "t20260806_34040891.html",
)


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
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def main():
    out = {}
    for url in URLS:
        html = fetch(url)
        title = re.search(r"<title>(.*?)</title>", html, re.S)
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        attachments = []
        for href in re.findall(r'href="([^"]+)"', html):
            low = href.lower()
            if any(ext in low for ext in (".pdf", ".xls", ".xlsx", ".doc",
                                          ".docx", ".zip", ".csv")):
                attachments.append(urllib.parse.urljoin(url, href))
        out[url] = {"title": (title.group(1).strip() if title else ""),
                    "bytes": len(html),
                    "attachments": sorted(set(attachments)),
                    "text_head": text[:600]}
        print("==", url)
        print("title:", out[url]["title"])
        print("attachments:", out[url]["attachments"])
        print("head:", out[url]["text_head"][:300])
    with open("logs/hunan_probe.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("DONE")


if __name__ == "__main__":
    main()
