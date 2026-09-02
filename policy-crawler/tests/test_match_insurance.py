# -*- coding: utf-8 -*-
"""分子层医保匹配测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from match_insurance_molecules import catalog_name_keys, find_matches  # noqa: E402


class TestMatchInsurance(unittest.TestCase):
    def test_catalog_name_keys(self):
        keys = catalog_name_keys("西格列汀二甲双胍Ⅰ\n西格列汀二甲双胍Ⅱ")
        self.assertIn("西格列汀二甲双胍", keys)
        self.assertEqual(catalog_name_keys("利拉鲁肽（H）注射液"), {"利拉鲁肽"})

    def test_find_matches_normalizes_salt_and_form(self):
        entries = [
            {"entry_id": 1, "name": "马来酸阿法替尼片"},
            {"entry_id": 2, "name": "奥希替尼"},
            {"entry_id": 3, "name": "不存在药"},
        ]
        molecules = [
            {"molecule_id": 11, "generic_name": "阿法替尼"},
            {"molecule_id": 12, "generic_name": "甲磺酸奥希替尼"},
        ]
        matches = find_matches(entries, molecules)
        self.assertEqual(matches.get(1), [11])
        self.assertEqual(matches.get(2), [12])
        self.assertNotIn(3, matches)

    def test_find_matches_multi_manufacturer_one_molecule(self):
        entries = [{"entry_id": 1, "name": "阿托伐他汀钙"}]
        molecules = [{"molecule_id": 21, "generic_name": "阿托伐他汀钙"}]
        matches = find_matches(entries, molecules)
        self.assertEqual(matches.get(1), [21])


if __name__ == "__main__":
    unittest.main()
