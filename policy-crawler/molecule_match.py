# -*- coding: utf-8 -*-
"""目录/名单药名 → 本库分子（drug_molecule）匹配器。

背景：drug_molecule 里存在同词干重复行（如「二甲双胍」与「二甲双胍缓释」、
「曲妥珠单抗」与「注射用曲妥珠单抗」）。按 molecule_key 匹配时会出现
「一对多」，若一律判为歧义就会大量漏挂。

规则（可解释、可复核）：
1. 先按 normalize.molecule_key 归一取候选；
2. 候选唯一 → 直接命中；
3. 候选多个 → 选「分子名作为子串在目录药名中出现且最长」的那个；
   没有任何候选名出现在目录药名中时，判定为无命中（不猜测）。

返回 (molecule_id 或 None, 匹配方式)。
"""
import re

from normalize import molecule_key, norm_roman, to_half_width


def normalize_catalog_name(name):
    """目录药名归一：全角→半角、罗马数字统一、去空格。"""
    t = norm_roman(to_half_width(name or ""))
    return re.sub(r"[\s\u3000]+", "", t)


def build_index(molecule_rows):
    """molecule_rows: [(molecule_id, generic_name), ...] → {molecule_key: [(id, name)]}"""
    index = {}
    for mid, name in molecule_rows:
        key = molecule_key(name)
        if key:
            index.setdefault(key, []).append((mid, name))
    return index


def pick_molecule(catalog_name, index):
    """按上述规则返回 (molecule_id, 匹配方式)：exact / longest-stem / none。"""
    norm = normalize_catalog_name(catalog_name)
    if not norm:
        return None, "none"
    candidates = index.get(molecule_key(catalog_name), [])
    if not candidates:
        return None, "none"
    if len(candidates) == 1:
        return candidates[0][0], "exact"
    scored = []
    for mid, name in candidates:
        stem = normalize_catalog_name(name)
        if stem and stem in norm:
            scored.append((len(stem), mid))
    if not scored:
        return None, "ambiguous"
    scored.sort(reverse=True)
    # 最长词干并列时视为不确定，避免误挂
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None, "ambiguous"
    return scored[0][1], "longest-stem"
