import json
import os
import tempfile
import threading
import unittest
import urllib.request
from urllib.parse import quote

from models import Policy
from pipeline import Pipeline
from serve import serve
from store import SqliteStore


class TestServe(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = SqliteStore(os.path.join(self.tmpdir, "s.db"))
        Pipeline(self.store).process([
            Policy(title="国家药监局关于药品经营许可证管理的通知", issuing_authority="国家药监局",
                   publish_date="2026-08-01", source_url="https://x.gov.cn/1.html", content="药品经营许可"),
            Policy(title="国家医保局关于开展国家药品集采的通知", issuing_authority="国家医保局",
                   publish_date="2026-07-15", source_url="https://x.gov.cn/2.html", content="集采 带量采购"),
        ])
        self.httpd = serve(self.store, port=0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path):
        encoded = quote(path, safe="/?=&")
        with urllib.request.urlopen("http://127.0.0.1:{}{}".format(self.port, encoded)) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def request_headers(self, path, method="GET"):
        req = urllib.request.Request(
            "http://127.0.0.1:{}{}".format(self.port, quote(path, safe="/?=&")),
            method=method,
        )
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers)

    def test_policies_endpoint(self):
        status, body = self.get("/api/policies?keyword=集采")
        self.assertEqual(status, 200)
        self.assertEqual(body["total"], 1)
        self.assertIn("国家药品集采", body["items"][0]["title"])

    def test_policy_detail_endpoint(self):
        status, body = self.get("/api/policies")
        pid = body["items"][0]["id"]
        status, detail = self.get("/api/policies/{}".format(pid))
        self.assertEqual(status, 200)
        self.assertIn("title", detail)

    def test_scenarios_endpoints(self):
        status, body = self.get("/api/scenarios")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["items"]), 6)
        status, matched = self.get("/api/scenarios/sc_vbp/policies")
        self.assertEqual(status, 200)
        self.assertEqual(len(matched["items"]), 1)

    def test_stats_endpoint(self):
        status, body = self.get("/api/stats/latest")
        self.assertEqual(status, 200)
        self.assertEqual(body["today"], 2)

    def test_health_endpoint(self):
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["policies"], 2)
        self.assertIn("nmpa", body["sources_enabled"])

    def test_cors_headers_on_all_get(self):
        status, headers = self.request_headers("/api/policies")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")

    def test_options_preflight(self):
        status, headers = self.request_headers("/api/policies", method="OPTIONS")
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")
        self.assertIn("GET", headers.get("Access-Control-Allow-Methods", ""))

    def test_invalid_page_param_falls_back(self):
        status, body = self.get("/api/policies?page=abc&size=999")
        self.assertEqual(status, 200)
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["size"], 100)

    def test_frontend_served_at_root(self):
        with urllib.request.urlopen("http://127.0.0.1:{}/".format(self.port)) as r:
            html = r.read().decode("utf-8")
            self.assertEqual(r.status, 200)
            self.assertIn("text/html", r.headers.get("Content-Type", ""))
            self.assertIn("政策信息聚合", html)


if __name__ == "__main__":
    unittest.main()
