# -*- coding: utf-8 -*-
"""Parse the saved 全国药品集采准入支持系统.html to find real data endpoints."""
import io
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PATH = r"C:\Users\YUWZZ\Desktop\html_pages\全国药品集采准入支持系统.html"


def main():
    h = open(PATH, encoding="utf-8", errors="replace").read()
    print("LEN", len(h))
    m = re.search(r"<title[^>]*>(.*?)</title>", h, re.S)
    print("TITLE", (m.group(1).strip() if m else "")[:120])
    urls = sorted(set(re.findall(r"https?://[^\s\"'<>)]+", h)))
    print("URLS", len(urls))
    for u in urls[:60]:
        print(" ", u[:200])
    refs = sorted(set(re.findall(r"""(?:src|href|action|url)\s*=\s*["']([^"']+)["']""", h)))
    print("REFS", len(refs))
    for r in refs[:60]:
        if r.startswith("http") or r.startswith("/") or r.startswith("."):
            print(" ", r[:200])
    # API-looking strings in inline scripts
    apis = sorted(set(re.findall(r"['\"](/[A-Za-z0-9_./-]{3,})['\"]", h)))
    print("API-LIKE", len(apis))
    for a in apis[:80]:
        print(" ", a)


if __name__ == "__main__":
    main()
