# -*- coding: utf-8 -*-
"""病种/领域分类规则测试（Wave-1）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from disease_rules import (  # noqa: E402
    RULES_VERSION,
    classify,
    classify_by_name,
    is_clean_text,
    is_indication_section,
)


class TestClassify(unittest.TestCase):
    def test_lung_cancer_from_official_text(self):
        text = ("本品单药适用于治疗表皮生长因子受体（EGFR）基因具有敏感突变的"
                "局部晚期或转移性非小细胞肺癌(NSCLC)成人患者。")
        r = classify(text, official=True)
        self.assertEqual(r["area"], "肿瘤")
        self.assertEqual(r["disease"], "肺癌")
        self.assertEqual(r["sub_disease"], "EGFR突变")
        self.assertEqual(r["confidence"], "高")

    def test_sc_lung_cancer_not_matched_inside_nsclc(self):
        """「非小细胞肺癌」不得被误判为「小细胞肺癌」亚型。"""
        r = classify("存在HER2激活突变的局部晚期或转移性非小细胞肺癌（NSCLC）",
                     official=True)
        self.assertEqual(r["disease"], "肺癌")
        self.assertNotEqual(r["sub_disease"], "小细胞肺癌")

    def test_lymphoma_kinase_not_matched_as_lymphoma(self):
        """「间变性淋巴瘤激酶」不得被误判为淋巴瘤。"""
        r = classify("本品适用于间变性淋巴瘤激酶（ALK）阳性的非小细胞肺癌",
                     official=True)
        self.assertEqual(r["disease"], "肺癌")

    def test_negated_disease_is_dropped(self):
        """「不适用于治疗1型糖尿病」属限制性表述，不计入病种。"""
        r = classify("4、重要的使用限制 本品不适用于治疗1型糖尿病或糖尿病酮症酸中毒。")
        self.assertNotEqual(r["disease"], "1型糖尿病")

    def test_first_indication_wins(self):
        text = ("1、用于2型糖尿病成人患者：单药治疗。"
                "2、用于心力衰竭成人患者：降低心血管死亡风险。"
                "3、用于慢性肾脏病成人患者。"
                "4、重要的使用限制 本品不适用于治疗1型糖尿病。")
        r = classify(text, official=True)
        self.assertEqual(r["disease"], "2型糖尿病")

    def test_confidence_levels(self):
        official = classify("用于治疗中重度斑块状银屑病的成人患者", official=True)
        short = classify("斑块状银屑病", official=False)
        self.assertEqual(official["confidence"], "高")
        self.assertEqual(short["confidence"], "中")

    def test_area_only_fallback(self):
        r = classify("本品用于肿瘤患者的支持治疗")
        self.assertEqual(r["area"], "肿瘤")
        self.assertEqual(r["disease"], "")
        self.assertEqual(r["confidence"], "低")

    def test_empty_text(self):
        r = classify("")
        self.assertEqual(r["area"], "")
        self.assertEqual(r["version"], RULES_VERSION)

    def test_tree_aligned_areas(self):
        """分类产出的领域需与前端 DISEASE_TREE 的领域命名一致。"""
        allowed = {"肿瘤", "代谢", "心血管", "自免疫", "罕见病", "感染",
                   "呼吸", "消化", "神经", "精神", "泌尿", "血液", "眼科",
                   "皮肤"}
        for text in ("用于心力衰竭成人患者", "用于高胆固醇血症患者",
                     "用于2型糖尿病成人患者", "用于血友病A患者"):
            area = classify(text, official=True)["area"]
            self.assertIn(area, allowed)


class TestSectionQuality(unittest.TestCase):
    def test_indication_section_accepted(self):
        text = "1、用于2型糖尿病成人患者：可作为单药治疗，改善血糖控制。"
        self.assertTrue(is_indication_section(text))

    def test_adverse_reaction_section_rejected(self):
        text = ("在许多上市后报告中，尤其是在1型糖尿病患者中，出现酮症酸中毒，"
                "不良反应包括恶心、呕吐。")
        self.assertFalse(is_indication_section(text))
        self.assertFalse(is_clean_text(text))


class TestInnStem(unittest.TestCase):
    def test_stem_fallback_is_low_confidence(self):
        r = classify_by_name("二甲双胍格列本脲")
        self.assertEqual(r["area"], "代谢")
        self.assertEqual(r["disease"], "2型糖尿病")
        self.assertEqual(r["confidence"], "低")

    def test_unknown_name(self):
        self.assertEqual(classify_by_name("某个不存在的药")["area"], "")


if __name__ == "__main__":
    unittest.main()
