# -*- coding: utf-8 -*-
"""Probe the two batch-12 procurement PDFs' layout before building the importer."""
import io
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pdfplumber

FILES = {
    "result": r"C:\Users\YUWZZ\Desktop\html_pages\第12批国家组织药品集中带量采购中选结果表（GY-YD2026-1）_202608061786007462909.pdf",
    "supply": r"C:\Users\YUWZZ\Desktop\html_pages\第12批国家组织药品集中带量采购中选品种供应清单（GY-YD2026-1）_202608061786007479657.pdf",
}


def main():
    key = "supply"
    path = FILES[key]
    with pdfplumber.open(path) as pdf:
        print("pages", len(pdf.pages))
        first = pdf.pages[0]
        tables = first.extract_tables()
        t = tables[0]
        print("HEADER", t[0])
        for row in t[1:4]:
            print("ROW", row)
        full = "\n".join((p.extract_text() or "") for p in pdf.pages[:6])
        for kw in ("价格", "元/", "计价", "单位"):
            idx = full.find(kw)
            print("KW", kw, "found" if idx >= 0 else "no")
            if idx >= 0:
                print(" ...", full[max(0, idx-160):idx+160].replace("\n", " | "))


if __name__ == "__main__":
    main()
