# -*- coding: utf-8 -*-
"""Deduped coverage report for the postmarket (channel-2) leaflet crawl.

Row-level statuses over-count because one drug name may map to many product
rows (different specs/manufacturers). This tool reports by unique normalized
drug name so the real coverage gap is visible.

Usage:
    python tools/audit_pm_coverage.py --results logs/cde_pm_full.jsonl
"""
import argparse
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from normalize import norm_roman, to_half_width  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def name_key(name):
    return norm_roman(to_half_width(name or "")).strip() or (name or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", default="logs/cde_pm_coverage_dedup.txt")
    args = ap.parse_args()

    rows = []
    with open(args.results, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rec["_key"] = name_key(rec.get("name"))
            rows.append(rec)

    by_key = collections.defaultdict(list)
    for r in rows:
        by_key[r["_key"]].append(r)

    status_rows = collections.Counter(r.get("status") for r in rows)
    status_names = collections.Counter()
    for key, recs in by_key.items():
        # one unique name -> single status priority ok > ambiguous > not_found
        st = ("ok" if any(r.get("status") == "ok" for r in recs)
              else "ambiguous" if any(r.get("status") == "ambiguous"
                                      for r in recs)
              else recs[0].get("status"))
        status_names[st] += 1

    dup_names = sorted(
        ((len(v), k) for k, v in by_key.items() if len(v) > 1), reverse=True)
    nf_names = sorted({r["_key"] for r in rows
                       if r.get("status") == "not_found"})

    lines = ["=== CDE channel-2 coverage (deduped by drug name) ==="]
    lines.append("rows=%d | unique names=%d" % (len(rows), len(by_key)))
    lines.append("by row  : " + json.dumps(dict(status_rows), ensure_ascii=False))
    lines.append("by name : " + json.dumps(dict(status_names), ensure_ascii=False))
    lines.append("\nMost duplicated names (rows):")
    for cnt, key in dup_names[:20]:
        lines.append("  %4d  %s" % (cnt, key))
    lines.append("\nUnique not-found names (%d):" % len(nf_names))
    for key in nf_names:
        lines.append("  " + key)
    report = "\n".join(lines)
    print(report[:4000])
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)
    print("\nSAVED", args.out)


if __name__ == "__main__":
    main()
