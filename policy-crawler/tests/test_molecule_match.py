# -*- coding: utf-8 -*-
"""目录药名 → 分子匹配器测试（Wave-1）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from molecule_match import build_index, normalize_catalog_name, pick_molecule  # noqa: E402


ROWS = [
    (1, "二甲双胍"),
    (2, "二甲双胍缓释"),
    (3, "曲妥珠单抗"),
    (4, "注射用曲妥珠单抗"),
    (5, "奥希替尼"),
]


class TestMoleculeMatch(unittest.TestCase):
    def setUp(self):
        self.index = build_index(ROWS)

    def test_normalize_strips_spaces(self):
        self.assertEqual(normalize_catalog_name(" 盐酸 二甲双胍 片 "),
                         "盐酸二甲双胍片")

    def test_unique_candidate(self):
        mid, how = pick_molecule("奥希替尼片", self.index)
        self.assertEqual(mid, 5)
        self.assertEqual(how, "exact")

    def test_longest_stem_preferred(self):
        """同词干重复行时选最长可解释词干：缓释片 → 「二甲双胍缓释」。"""
        mid, how = pick_molecule("盐酸二甲双胍缓释片(Ⅳ)", self.index)
        self.assertEqual(mid, 2)
        self.assertEqual(how, "longest-stem")

    def test_plain_form_matches_plain_molecule(self):
        mid, how = pick_molecule("二甲双胍片", self.index)
        self.assertEqual(mid, 1)
        self.assertEqual(how, "longest-stem")

    def test_no_candidate(self):
        mid, how = pick_molecule("某个不存在的药片", self.index)
        self.assertIsNone(mid)
        self.assertEqual(how, "none")

    def test_tie_is_treated_as_ambiguous(self):
        # 两个等长词干同时命中目录药名 → 不猜，返回 ambiguous
        index = {"阿司匹林": [(1, "匹林"), (2, "司匹")]}
        mid, how = pick_molecule("阿司匹林片", index)
        self.assertEqual(how, "ambiguous")
        self.assertIsNone(mid)

    def test_salt_suffix_prefers_longer_stem(self):
        """「阿托伐他汀钙片」应命中「阿托伐他汀钙」（更长且更具体的词干）。"""
        index = build_index([(1, "阿托伐他汀"), (2, "阿托伐他汀钙")])
        mid, how = pick_molecule("阿托伐他汀钙片", index)
        self.assertEqual(mid, 2)
        self.assertEqual(how, "longest-stem")


if __name__ == "__main__":
    unittest.main()
