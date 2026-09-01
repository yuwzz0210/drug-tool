# -*- coding: utf-8 -*-
"""数据清洗规则测试（数据字典 v1.0 配套）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalize import (  # noqa: E402
    KNOWN_CORRECTIONS,
    molecule_key,
    norm_roman,
    split_manufacturers,
    strip_class_markers,
    strip_dosage_form,
    strip_salt,
    to_half_width,
)


class TestNormalize(unittest.TestCase):
    def test_half_width(self):
        # 全角括号转半角；罗马数字归一是 norm_roman 的职责
        self.assertEqual(to_half_width("阿托伐他汀（Ⅰ）"), "阿托伐他汀(Ⅰ)")
        self.assertEqual(to_half_width("；：，．"), ";:.,")
        self.assertEqual(to_half_width("ＡＢＣ１２３"), "ABC123")

    def test_roman(self):
        self.assertEqual(norm_roman("二甲双胍恩格列净片（Ⅰ）"), "二甲双胍恩格列净片（I）")
        self.assertEqual(norm_roman("维格列汀Ⅱ"), "维格列汀II")
        self.assertEqual(norm_roman("ⅲ"), "III")

    def test_class_markers(self):
        self.assertEqual(strip_class_markers("利拉鲁肽（H）注射液"), "利拉鲁肽注射液")
        self.assertEqual(strip_class_markers("司美格鲁肽(H)"), "司美格鲁肽")

    def test_dosage_form_and_salt(self):
        self.assertEqual(strip_dosage_form("乌帕替尼缓释片"), "乌帕替尼缓释")
        self.assertEqual(strip_dosage_form("甲氨蝶呤片"), "甲氨蝶呤")
        self.assertEqual(strip_salt("甲磺酸奥希替尼"), "奥希替尼")
        self.assertEqual(strip_salt("盐酸二甲双胍"), "二甲双胍")

    def test_molecule_key(self):
        self.assertEqual(molecule_key("利拉鲁肽（H）注射液"), "利拉鲁肽")
        self.assertEqual(molecule_key("甲磺酸阿美替尼片"), "阿美替尼")
        self.assertEqual(molecule_key("二甲双胍恩格列净片（Ⅰ）"), "二甲双胍恩格列净")
        self.assertEqual(molecule_key("司美格鲁肽(口服)"), "司美格鲁肽")

    def test_split_manufacturers(self):
        self.assertEqual(
            split_manufacturers("康方药业有限公司;中山康方生物医药有限公司"),
            ["康方药业有限公司", "中山康方生物医药有限公司"],
        )
        self.assertEqual(
            split_manufacturers("原液生产企业：珠海联邦生物医药有限公司；制剂生产企业：（1）珠海联邦生物医药有限公司（2）珠海联邦制药股份有限公司"),
            ["珠海联邦生物医药有限公司", "珠海联邦制药股份有限公司"],
        )
        # 已知笔误修正
        self.assertEqual(
            split_manufacturers("浙江江北药业有限公司,国药集国国瑞药业有限公司"),
            ["浙江江北药业有限公司", KNOWN_CORRECTIONS["国药集国国瑞药业有限公司"]],
        )


if __name__ == "__main__":
    unittest.main()
