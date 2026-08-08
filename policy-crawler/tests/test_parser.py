import os
import unittest

from parsers import PARSERS, NmpaParser


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def read(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


class TestNmpaParser(unittest.TestCase):
    def setUp(self):
        self.parser = NmpaParser()

    def test_registry_has_nmpa(self):
        self.assertIn("nmpa", PARSERS)

    def test_parse_list_two_items_with_fields(self):
        items = self.parser.parse_list(read("nmpa_list.html"))
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertIn("药品经营质量管理规范现场检查指导原则", first["title"])
        self.assertTrue(first["url"].startswith("https://www.nmpa.gov.cn/"))
        self.assertEqual(first["date"], "2026-07-25")
        self.assertEqual(items[1]["title"], "国家药监局关于进一步做好药品追溯体系建设的通知")
        self.assertEqual(items[1]["date"], "2026-07-10")

    def test_parse_real_structure_with_noise_filter(self):
        """真实 NMPA 页面结构：日期在锚点之后；导航噪音需排除。"""
        items = self.parser.parse_list(
            read("nmpa_list_real.html"),
            keep_paths=["/xxgk/fgwj/gzwj/gzwjyp/"],
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "关于中药品种保护审评相关工作调整有关事宜的通知（药审业〔2026〕250号）")
        self.assertEqual(items[0]["date"], "2026-06-25")
        self.assertEqual(items[1]["title"], "国家药监局综合司关于印发处方药网络零售合规指南的通知")
        self.assertEqual(items[1]["date"], "2026-05-25")
        joined = " ".join(it["title"] for it in items)
        self.assertNotIn("网站声明", joined)
        self.assertNotIn("联系我们", joined)

    def test_parse_detail_fields(self):
        detail = self.parser.parse_detail(read("nmpa_detail.html"))
        self.assertIn("药品经营质量管理规范现场检查指导原则", detail["title"])
        self.assertEqual(detail["publish_date"], "2026-07-25")
        self.assertEqual(detail["doc_number"], "国药监药管〔2026〕18号")
        self.assertIn("为贯彻实施《药品管理法》", detail["content"])
        self.assertIn("2026年10月1日起施行", detail["content"])

    def test_parse_real_detail_page(self):
        """真实 NMPA 详情页：正文在 <div class='text'>，需排除页头 app 链接噪音。"""
        detail = self.parser.parse_detail(read("nmpa_detail_real.html"))
        self.assertIn("政策解读", detail["title"])
        self.assertEqual(detail["publish_date"], "2026-07-29")
        self.assertIn("制定的背景和目的是什么", detail["content"])
        self.assertNotIn("中国药监App", detail["content"])
        self.assertGreater(len(detail["content"]), 500)

    def test_nhsa_list_with_keep_paths(self):
        from parsers import NhsaParser

        items = NhsaParser().parse_list(read("nhsa_list.html"), keep_paths=["/art/"])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "国家医保局关于做好2026年医保药品目录调整工作的通知")
        self.assertEqual(items[0]["date"], "2026-07-20")
        self.assertNotIn("联系我们", " ".join(it["title"] for it in items))

    def test_nhsa_detail_with_attachments(self):
        from parsers import NhsaParser

        detail = NhsaParser().parse_detail(read("nhsa_detail.html"))
        self.assertIn("医保药品目录调整", detail["title"])
        self.assertEqual(detail["publish_date"], "2026-07-20")
        self.assertEqual(detail["doc_number"], "医保发〔2026〕18号")
        self.assertIn("现就做好2026年医保药品目录调整工作", detail["content"])
        self.assertTrue(any(".pdf" in att.get("url", "") for att in detail["attachments"]))

    def test_nhc_list_and_detail(self):
        from parsers import NhcParser

        parser = NhcParser()
        items = parser.parse_list(read("nhc_list.html"), keep_paths=["/fzs/"])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["date"], "2026-07-18")
        detail = parser.parse_detail(read("nhc_detail.html"))
        self.assertIn("药事管理", detail["title"])
        self.assertEqual(detail["doc_number"], "国卫办医函〔2026〕120号")
        self.assertIn("促进合理用药", detail["content"])

    def test_nhsa_real_detail_page(self):
        """真实 NHSA 详情页：标题/文号取 CMS 标记，日期取信息公开表格，正文含下载链接。"""
        from parsers import NhsaParser

        detail = NhsaParser().parse_detail(read("nhsa_detail_real.html"))
        self.assertEqual(
            detail["title"],
            "国家医保局办公室 国家卫生健康委办公厅关于确定医保支持基层医疗卫生服务发展重点联系点的通知",
        )
        self.assertEqual(detail["publish_date"], "2026-07-17")
        self.assertEqual(detail["doc_number"], "医保办函〔2026〕52号")
        self.assertIn("文件下载链接", detail["content"])
        self.assertTrue(any("downfile.jsp" in att.get("url", "") for att in detail["attachments"]))

    def test_nhsa_real_list_page(self):
        """真实 NHSA 政策法规列表：索引号 2026-02-00018 不能被误当成日期。"""
        from parsers import NhsaParser

        items = NhsaParser().parse_list(
            read("nhsa_list_real.html"), keep_paths=["/art/"],
        )
        self.assertEqual(len(items), 15)
        first = items[0]
        self.assertEqual(
            first["title"],
            "国家医保局办公室 国家卫生健康委办公厅关于确定医保支持基层医疗卫生服务发展重点联系点的通知",
        )
        self.assertEqual(first["date"], "2026-07-17")
        self.assertEqual(first["url"], "https://www.nhsa.gov.cn/art/2026/7/17/art_104_21472.html")

    def test_nhc_real_detail_page(self):
        """真实 NHC 详情页：正文在 #xw_box，标题/日期来自 meta，来源为法规司。"""
        from parsers import NhcParser

        detail = NhcParser().parse_detail(read("nhc_detail_real.html"))
        self.assertEqual(detail["title"], "关于发布《感染性腹泻诊断标准》等4项法定传染病诊断标准的通告")
        self.assertEqual(detail["publish_date"], "2026-07-29")
        self.assertEqual(detail["doc_number"], "国卫通〔2026〕10号")
        self.assertEqual(detail["issuing_authority"], "法规司")
        self.assertIn("感染性腹泻诊断标准", detail["content"])
        self.assertNotIn("$(function", detail["content"])
        self.assertTrue(any(att.get("url", "").endswith(".pdf") for att in detail["attachments"]))

    def test_nhc_real_list_page(self):
        """真实 NHC 政策文件列表：只保留 /fzs/<栏目>/<yyyymm>/*.shtml 条目，排除导航噪音。"""
        from parsers import NhcParser

        items = NhcParser().parse_list(
            read("nhc_list_real.html"), keep_paths=["/fzs/"],
        )
        self.assertEqual(len(items), 24)
        self.assertEqual(items[0]["title"], "关于发布《感染性腹泻诊断标准》等4项法定传染病诊断标准的通告")
        self.assertEqual(items[0]["date"], "2026-07-29")
        joined = " ".join(it["title"] for it in items)
        self.assertNotIn("工作动态", joined)
        self.assertNotIn("政策文件", joined)
        self.assertNotIn("专题专栏", joined)

    def test_registry_has_new_sources(self):
        self.assertIn("nhsa", PARSERS)
        self.assertIn("nhc", PARSERS)


if __name__ == "__main__":
    unittest.main()
