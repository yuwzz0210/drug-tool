# -*- coding: utf-8 -*-
"""Inspect a saved NMPA datasearch page: shell vs real rows / embedded JSON."""
import io
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PATH = r"C:\Users\YUWZZ\Desktop\html_pages\国家药品监督管理局数据查询.html"


def main():
    h = open(PATH, encoding="utf-8", errors="replace").read()
    print("LEN", len(h))
    m = re.search(r"<title[^>]*>(.*?)</title>", h, re.S)
    print("TITLE", (m.group(1).strip() if m else "")[:120])
    print("approval-like count", len(re.findall(r"国药准字[HSZJ]\d+", h)))
    print("search-result url", "search-result" in h)
    print("dataCenter mentions", h.count("dataCenter"))
    # table rows sample
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S)
    print("tr count", len(rows))
    for r in rows[:6]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        print("  ", cells[:10])
    # embedded JSON-looking blobs
    for pat in (r'"total"\s*:\s*\d+', r'\.\.\.'):
        pass
    tot = re.findall(r'"total"\s*:\s*(\d+)', h)
    print("embedded total occurrences", len(tot), tot[:5])
    # scripts referencing dataCenter or api paths
    urls = sorted(set(re.findall(r"[^\"']*/datasearch/[^\"']*[^\"']", h)))
    print("datasearch refs", urls[:10])


if __name__ == "__main__":
    main()
