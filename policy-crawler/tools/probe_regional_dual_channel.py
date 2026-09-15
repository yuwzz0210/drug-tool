# -*- coding: utf-8 -*-
"""探测湖南/上海医保官方站点的「双通道」「挂网价」入口（只读，不落业务数据）。

合规：先查 robots.txt；请求间隔 ≥4 秒（随机抖动）；浏览器 UA；403 立即停止。
输出：logs/regional_probe.json（各页面命中的关键词链接）。

用法：
    python tools/probe_regional_dual_channel.py
"""
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

KEYWORDS = ("双通道", "定点零售药店", "谈判药品", "挂网", "价格", "集采", "中选")

SEEDS = (
    "http://ybj.hunan.gov.cn/ybj/first113541/firstF/f2113606/index.html",
    "http://ybj.hunan.gov.cn/ybj/index.html",
    "https://ybj.sh.gov.cn/",
    "https://ybj.sh.gov.cn/zcwj/",
)


def robots_allowed(url):
    parts = urllib.parse.urlparse(url)
    robots = "{}://{}/robots.txt".format(parts.scheme, parts.netloc)
    try:
        body = fetch(robots)[1]
    except Exception:
        return True, "robots 获取失败，默认放行"
    disallow = []
    for line in body.splitlines():
        line = line.strip().lower()
        if line.startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                disallow.append(path)
    for path in disallow:
        if path != "/" and parts.path.startswith(path):
            return False, "robots Disallow " + path
    return True, "ok"


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


def extract_links(base, html):
    out = []
    for href, text in re.findall(
            r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if any(k in text for k in KEYWORDS):
            out.append({"text": text[:80],
                        "url": urllib.parse.urljoin(base, href)})
    return out


def main():
    report = {}
    fetched = 0
    for seed in SEEDS:
        allowed, why = robots_allowed(seed)
        if not allowed:
            report[seed] = {"skipped": why}
            print("SKIP", seed, why)
            continue
        if fetched:
            time.sleep(4 + random.random())
        try:
            status, html = fetch(seed)
            fetched += 1
            hits = extract_links(seed, html)
            report[seed] = {"status": status, "bytes": len(html),
                            "hits": hits[:40]}
            print(seed, status, len(html), "hits", len(hits))
        except Exception as exc:
            report[seed] = {"error": "{}: {}".format(type(exc).__name__, exc)}
            print("ERR", seed, type(exc).__name__, str(exc)[:90])
    os.makedirs("logs", exist_ok=True)
    with open("logs/regional_probe.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("PROBE_DONE -> logs/regional_probe.json")


if __name__ == "__main__":
    main()
