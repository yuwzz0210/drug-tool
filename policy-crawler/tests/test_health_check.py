import os
import tempfile
import unittest

from health_check import check_db, check_sources, run


class TestHealthCheck(unittest.TestCase):
    def test_check_db_ok_on_fresh_file(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            ok, detail = check_db(path)
            self.assertTrue(ok)
            self.assertIn("数据库正常", detail)
        finally:
            os.unlink(path)

    def test_check_db_fails_on_bad_path(self):
        ok, detail = check_db(os.path.join(tempfile.gettempdir(), "no_such_dir_xyz", "x.db"))
        self.assertFalse(ok)
        self.assertIn("异常", detail)

    def test_sources_all_ok(self):
        results = check_sources(fetch=lambda url: 200)
        self.assertTrue(results)
        self.assertTrue(all(r["ok"] for r in results))

    def test_sources_403_flagged_blocked(self):
        results = check_sources(fetch=lambda url: 403)
        self.assertTrue(results)
        self.assertTrue(all(not r["ok"] for r in results))
        self.assertIn("反爬", results[0]["detail"])

    def test_run_aggregates_db_and_sources(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            report = run(db_path=path, fetch=lambda url: 200)
            self.assertTrue(report["ok"])
            self.assertTrue(report["db"]["ok"])
            self.assertGreaterEqual(len(report["sources"]), 1)
            self.assertIn("checked_at", report)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
