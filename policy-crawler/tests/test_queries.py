import datetime
import os
import tempfile
import unittest

from models import Policy
from pipeline import Pipeline
from queries import (
    get_policy,
    list_policies,
    list_scenarios,
    scenario_policies,
    stats_latest,
    update_validity,
)
from store import SqliteStore


class TestQueries(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = SqliteStore(os.path.join(self.tmpdir, "q.db"))
        Pipeline(self.store).process([
            Policy(title="国家药监局关于药品经营许可证管理的通知", issuing_authority="国家药监局",
                   publish_date="2026-08-01", source_url="https://x.gov.cn/1.html",
                   content="药品经营许可 质量管理规范 GSP", tags='["药品经营"]'),
            Policy(title="国家医保局关于开展国家药品集采的通知", issuing_authority="国家医保局",
                   publish_date="2026-07-15", source_url="https://x.gov.cn/2.html",
                   content="集采 带量采购 中选", tags='["集采"]'),
            Policy(title="关于废止某药品追溯管理办法的通知", issuing_authority="国家卫健委",
                   publish_date="2026-06-01", source_url="https://x.gov.cn/3.html",
                   content="废止 追溯"),
        ])

    def test_list_keyword_filter(self):
        r = list_policies(self.store, keyword="集采")
        self.assertEqual(r["total"], 1)
        self.assertIn("国家药品集采", r["items"][0]["title"])

    def test_list_authority_and_pagination(self):
        r = list_policies(self.store, authority="医保局", size=10)
        self.assertEqual(r["total"], 1)
        p = list_policies(self.store, page=1, size=2)
        self.assertEqual(len(p["items"]), 2)
        self.assertEqual(p["total"], 3)

    def test_date_range(self):
        r = list_policies(self.store, date_from="2026-07-01", date_to="2026-07-31")
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["items"][0]["title"], "国家医保局关于开展国家药品集采的通知")

    def test_get_policy_by_id(self):
        rows = self.store.query_policies({})
        row = get_policy(self.store, rows[0]["id"])
        self.assertIsNotNone(row)
        self.assertIn("title", row)

    def test_scenarios_and_matching(self):
        scenarios = list_scenarios()
        self.assertEqual(len(scenarios), 6)
        items = scenario_policies(self.store, "sc_vbp")
        self.assertEqual(len(items), 1)
        self.assertIn("集采", items[0]["title"])
        self.assertEqual(scenario_policies(self.store, "sc_unknown"), [])

    def test_stats_latest(self):
        stats = stats_latest(self.store, days=7)
        self.assertEqual(stats["today"], 3)
        self.assertEqual(stats["week"], 3)

    def test_update_validity_rules(self):
        future = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
        self.assertEqual(update_validity({"title": "通知", "publish_date": future}), "未生效")
        self.assertEqual(update_validity({"title": "关于废止办法的通知", "publish_date": "2026-01-01"}), "废止")
        self.assertEqual(update_validity({"title": "普通通知", "publish_date": "2026-01-01"}), "有效")


if __name__ == "__main__":
    unittest.main()
