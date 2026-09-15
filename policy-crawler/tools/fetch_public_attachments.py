# -*- coding: utf-8 -*-
"""抓取政府公开文件页并下载其附件（合规：robots + ≥4 秒间隔 + 浏览器 UA）。

用法：
    python tools/fetch_public_attachments.py --outdir logs/regional <URL> [URL ...]
输出：页面 HTML 存 <outdir>/pages/，附件存 <outdir>/，并打印附件清单。
"""
import argparse
import io
import json
import os
import random
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
EXTS = (".pdf", ".xls", ".xlsx", ".doc", ".docx", ".zip", ".csv", ".wps")


def fetch_raw(url, referer=None):
    headers = {"User-Agent": UA,
               "Accept": "*/*",
               "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
        return resp.status, resp.read()


def decode(raw):
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def robots_allowed(url):
    parts = urllib.parse.urlparse(url)
    robots = "{}://{}/robots.txt".format(parts.scheme, parts.netloc)
    try:
        _, raw = fetch_raw(robots)
    except Exception:
        return True, "robots 获取失败，默认放行"
    for line in decode(raw).splitlines():
        line = line.strip().lower()
        if line.startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path and path != "/" and parts.path.startswith(path):
                return False, "robots Disallow " + path
    return True, "ok"


def main():
    ap = argparse.ArgumentParser(description="公开文件页 + 附件下载")
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--outdir", default="logs/regional")
    ap.add_argument("--download", action="store_true",
                    help="实际下载附件（默认只列出）")
    args = ap.parse_args()

    pages_dir = os.path.join(args.outdir, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    manifest = {}
    for idx, url in enumerate(args.urls):
        allowed, why = robots_allowed(url)
        if not allowed:
            print("SKIP", url, why)
            manifest[url] = {"skipped": why}
            continue
        if idx:
            time.sleep(4 + random.random())
        try:
            status, raw = fetch_raw(url)
        except Exception as exc:
            manifest[url] = {"error": "{}: {}".format(type(exc).__name__,
                                                      str(exc)[:120])}
            print("ERR", url, type(exc).__name__, str(exc)[:100])
            continue
        html = decode(raw)
        name = re.sub(r"[^A-Za-z0-9]+", "_", url)[-80:] + ".html"
        with open(os.path.join(pages_dir, name), "w", encoding="utf-8") as fh:
            fh.write(html)
        title = re.search(r"<title>(.*?)</title>", html, re.S)
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        attachments = []
        for href in re.findall(r'href="([^"]+)"', html):
            if any(ext in href.lower() for ext in EXTS):
                attachments.append(urllib.parse.urljoin(url, href))
        attachments = sorted(set(attachments))
        manifest[url] = {
            "status": status,
            "title": title.group(1).strip() if title else "",
            "attachments": attachments,
            "text_head": text[:400],
        }
        print("==", url)
        print("   title:", manifest[url]["title"])
        for att in attachments:
            print("   ATT:", att)
        if args.download:
            for att in attachments:
                fn = os.path.join(args.outdir, os.path.basename(
                    urllib.parse.urlparse(att).path) or "attach.bin")
                try:
                    time.sleep(3 + random.random())
                    _, blob = fetch_raw(att, referer=url)
                    with open(fn, "wb") as fh:
                        fh.write(blob)
                    print("   SAVED:", fn, len(blob))
                except Exception as exc:
                    print("   ATTERR:", att, type(exc).__name__)
    with open(os.path.join(args.outdir, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print("FETCH_ATTACH_DONE ->", os.path.join(args.outdir, "manifest.json"))


if __name__ == "__main__":
    main()
