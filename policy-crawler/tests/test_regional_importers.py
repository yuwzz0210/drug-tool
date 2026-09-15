# -*- coding: utf-8 -*-
"""区域导入器纯函数测试（湖南价格表 / 上海支付标准解析口径）。"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import import_shanghai_payment_standard as sh_pay  # noqa: E402
from import_regional_hunan import norm_approval, parse_price  # noqa: E402


class TestHunanHelpers(unittest.TestCase):
    def test_norm_approval(self):
        self.assertEqual(norm_approval(" 国药准字 H2023 4621 "), "国药准字H20234621")
        self.assertEqual(norm_approval("国药准字HJ20202000"), "国药准字HJ20202000")

    def test_parse_price(self):
        self.assertEqual(parse_price("430.00"), 430.0)
        self.assertEqual(parse_price("1,234.5元"), 1234.5)
        self.assertIsNone(parse_price(""))
        self.assertIsNone(parse_price("*"))
        self.assertIsNone(parse_price("0"))


class TestShanghaiPaymentHelpers(unittest.TestCase):
    def test_parse_period(self):
        start, end = sh_pay.parse_period("2026年1月1日至 2027年12月31日")
        self.assertEqual(start, "2026-01-01")
        self.assertEqual(end, "2027-12-31")

    def test_parse_period_single(self):
        start, end = sh_pay.parse_period("2026年1月1日至")
        self.assertEqual(start, "2026-01-01")
        self.assertEqual(end, "")

    def test_parse_period_empty(self):
        self.assertEqual(sh_pay.parse_period(""), ("", ""))

    def test_standard_regex(self):
        m = sh_pay.STANDARD_RE.match("52.60元(10mg/瓶)")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "52.60")


if __name__ == "__main__":
    unittest.main()
