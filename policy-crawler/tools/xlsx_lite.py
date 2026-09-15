# -*- coding: utf-8 -*-
"""极简 xlsx 读取器（标准库实现，无第三方依赖）。

仅支持 .xlsx（OOXML）：读取单元格值，按行返回列表。
用于解析政府公开名单附件（挂网价、双通道名单等）。
"""
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ROW_TAG = "{%s}row" % MAIN_NS
TAG_T = "{%s}t" % MAIN_NS


def _shared_strings(zf):
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out = []
    for si in root.findall("m:si", NS):
        out.append("".join(t.text or "" for t in si.iter(TAG_T)))
    return out


def _sheet_names(zf):
    root = ET.fromstring(zf.read("xl/workbook.xml"))
    names = []
    for sh in root.findall("m:sheets/m:sheet", NS):
        rid = sh.get("{http://schemas.openxmlformats.org/officeDocument/"
                     "2006/relationships}id")
        names.append((sh.get("name"), rid))
    return names


def _sheet_path(zf, rid):
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels:
        if rel.get("Id") == rid:
            target = rel.get("Target")
            if target.startswith("/"):
                return target.lstrip("/")
            return "xl/" + target.lstrip("./")
    return "xl/worksheets/sheet1.xml"


def _col_index(ref):
    letters = re.match(r"([A-Z]+)", ref or "").group(1)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def read_rows(path, sheet_index=0, max_rows=None):
    """读取指定工作表，返回 [row, ...]，row 为按列序补齐的字符串列表。"""
    with zipfile.ZipFile(path) as zf:
        shared = _shared_strings(zf)
        sheets = _sheet_names(zf)
        if sheet_index >= len(sheets):
            return []
        path_in_zip = _sheet_path(zf, sheets[sheet_index][1])
        rows = []
        for _, el in ET.iterparse(zf.open(path_in_zip), events=("end",)):
            if el.tag != ROW_TAG:
                continue
            cells = {}
            for c in el.findall("m:c", NS):
                ref = c.get("r") or ""
                ctype = c.get("t")
                value = c.find("m:v", NS)
                if ctype == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(TAG_T))
                elif value is None:
                    text = ""
                elif ctype == "s":
                    try:
                        text = shared[int(value.text)]
                    except (ValueError, IndexError):
                        text = ""
                else:
                    text = value.text or ""
                cells[_col_index(ref)] = text.strip()
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(i, "") for i in range(width)])
            el.clear()
            if max_rows and len(rows) >= max_rows:
                break
        return rows


def sheet_names(path):
    with zipfile.ZipFile(path) as zf:
        return [name for name, _ in _sheet_names(zf)]
