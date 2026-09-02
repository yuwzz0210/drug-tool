# -*- coding: utf-8 -*-
"""数据清洗规则（数据字典 v1.0 配套）：全角/罗马数字/厂家拆分/剂型与盐基剥离/分类标识。

用途：把「厂家 × 通用名+剂型」粒度聚合到「品种(molecule)」层，
消除 全角半角混用、罗马数字多写法、厂家分隔符混用、字段污染 等问题。
所有规则均配套单元测试（tests/test_normalize.py）。
"""
import re


FORM_SUFFIXES = (
    "片", "胶囊", "软胶囊", "注射液", "注射剂", "颗粒", "口服液", "口服溶液",
    "滴眼液", "栓剂", "气雾剂", "散剂", "丸", "丸剂", "糖浆", "干混悬剂",
    "喷雾剂", "凝胶剂", "乳膏剂", "软膏剂", "贴膏剂", "贴剂", "混悬剂",
    "溶液剂", "滴剂", "洗剂", "搽剂", "膜剂", "植入剂",
)

SALT_PREFIXES = (
    "盐酸", "甲磺酸", "苯磺酸", "枸橼酸", "柠檬酸", "马来酸", "富马酸",
    "酒石酸", "琥珀酸", "磷酸", "醋酸", "硫酸", "氢溴酸", "硝酸", "乳酸",
    "依地酸", "双羟萘酸", "甲苯磺酸", "对甲苯磺酸", "乙磺酸",
)

ROMAN_MAP = {
    "Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V", "Ⅵ": "VI",
    "Ⅶ": "VII", "Ⅷ": "VIII", "Ⅸ": "IX", "Ⅹ": "X",
    "ⅰ": "I", "ⅱ": "II", "ⅲ": "III", "ⅳ": "IV", "ⅴ": "V", "ⅵ": "VI",
    "ⅶ": "VII", "ⅷ": "VIII", "ⅸ": "IX", "ⅹ": "X",
}

# 人工核对的已知笔误（官方源照录，此处统一修正并留痕）
KNOWN_CORRECTIONS = {
    "国药集国国瑞药业有限公司": "国药集团国瑞药业有限公司",
}

_FULL_TO_HALF = {ord(c): ord(h) for c, h in zip(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ（）＜＞＝：；，．／％",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz()<>=:;.,/%",
)}


def to_half_width(text):
    """全角转半角（含括号/冒号/分号/逗号/数字/字母）。"""
    if not text:
        return ""
    return str(text).translate(_FULL_TO_HALF)


def norm_roman(text):
    """罗马数字统一为 ASCII：Ⅰ/ⅱ → I/II。"""
    if not text:
        return ""
    out = []
    for ch in str(text):
        out.append(ROMAN_MAP.get(ch, ch))
    return "".join(out)


def strip_class_markers(text):
    """剥离药名中括号分类标识：任意位置的（H）/（I~X）等短标识，以及尾部括号注记。"""
    if not text:
        return ""
    t = to_half_width(norm_roman(text)).strip()
    # 短字母/数字标识（H、I、II…），任意位置剥离
    t = re.sub(r"[（(][A-Za-z0-9]{1,2}[）)]", "", t).strip()
    # 尾部任意括号注记剥离（如 司美格鲁肽(口服) → 司美格鲁肽）
    t = re.sub(r"[（(][^（）()]*[）)]$", "", t).strip()
    return t


def strip_dosage_form(name):
    """剥离剂型后缀。"""
    for suffix in FORM_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def strip_salt(name):
    """剥离盐基前缀，如 甲磺酸阿美替尼 → 阿美替尼。"""
    for prefix in SALT_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix) + 1:
            return name[len(prefix):]
    return name


def molecule_key(generic_name):
    """品种聚合键：全角→半角、罗马归一、去括号标识、去剂型/修饰词/盐基/盐离子。

    覆盖 利拉鲁肽（H）注射液、二甲双胍恩格列净片（Ⅰ）、阿托伐他汀钙、
    马来酸阿法替尼片、注射用甲氨蝶呤、二甲双胍缓释 等写法归一。
    """
    name = strip_class_markers(generic_name)
    name = re.sub(r"[IVX]+$", "", name)                      # 尾部罗马数字 ASCII
    name = re.sub(r"(缓释|控释|肠溶|分散|泡腾|咀嚼|长效|速释)", "", name)  # 剂型修饰词
    name = re.sub(r"^注射用", "", name)                       # 注射用前缀
    name = strip_dosage_form(name)
    name = strip_salt(name)
    name = re.sub(r"(钙|钠|钾|镁|锌|铁|锂|锰|铜)$", "", name)  # 盐离子后缀
    return name.strip()


def split_manufacturers(text):
    """厂家拆分：支持 ; ； , ， 、 多分隔符；剥离角色说明（原液/制剂生产企业）与序号。"""
    if not text:
        return []
    t = to_half_width(str(text))
    t = re.sub(r"(原液|制剂|原料药|成品)生产企业[：:]?", "", t)
    parts = re.split(r"[;；,，、]+|[（(]\d+[）)]", t)
    out = []
    for p in parts:
        p = re.sub(r"[（(]\d+[）)]", "", p).strip()
        p = p.strip(" 　(（）)")
        if p and p not in out:
            out.append(KNOWN_CORRECTIONS.get(p, p))
    return out
