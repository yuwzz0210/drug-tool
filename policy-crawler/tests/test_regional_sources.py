import os
import tempfile
import unittest

from config import load_all_sources
from tools.build_regional_sources import build_regional_sources, write_regional_sources


SAMPLE_NAV = {
    "医保局": [
        {"name": "国家医疗保障局", "area": "国家", "portal_url": "http://www.nhsa.gov.cn/", "system_urls": []},
        {"name": "北京市医疗保障局", "area": "北京市", "portal_url": "http://ybj.beijing.gov.cn/", "system_urls": []},
    ],
    "药监局": [
        {"name": "湖南省药品监督管理局", "area": "湖南省", "portal_url": "http://mpa.hunan.gov.cn/", "system_urls": []},
    ],
    "卫健委": [
        {"name": "中华人民共和国国家卫生健康委员会", "area": "国家", "portal_url": "http://www.nhc.gov.cn/", "system_urls": []},
    ],
}


class TestRegionalSources(unittest.TestCase):
    def test_build_maps_parser_and_marks_disabled(self):
        srcs = build_regional_sources(SAMPLE_NAV)
        self.assertIn("nhsa_cn", srcs)
        self.assertIn("nhsa_bj", srcs)
        self.assertIn("nmpa_hn", srcs)
        self.assertIn("nhc_cn", srcs)
        self.assertEqual(srcs["nhsa_bj"]["parser"], "nhsa")
        self.assertEqual(srcs["nmpa_hn"]["parser"], "nmpa")
        self.assertEqual(srcs["nhc_cn"]["parser"], "nhc")
        self.assertEqual(srcs["nhsa_bj"]["area"], "北京市")
        self.assertEqual(srcs["nhsa_bj"]["base"], "http://ybj.beijing.gov.cn/")
        self.assertFalse(srcs["nhsa_bj"]["enabled"])

    def test_portal_dedupe(self):
        nav = {"医保局": [
            {"name": "A", "area": "国家", "portal_url": "http://x.gov.cn/", "system_urls": []},
            {"name": "B", "area": "国家", "portal_url": "http://x.gov.cn/", "system_urls": []},
        ]}
        srcs = build_regional_sources(nav)
        self.assertEqual(len([k for k in srcs if k.startswith("nhsa_")]), 1)

    def test_write_and_load_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "regional_sources.json")
            write_regional_sources(build_regional_sources(SAMPLE_NAV), path)
            merged = load_all_sources(regional_path=path)
            self.assertIn("nhsa", merged)
            self.assertIn("nhsa_bj", merged)
            self.assertEqual(merged["nhsa_bj"]["parser"], "nhsa")


if __name__ == "__main__":
    unittest.main()
