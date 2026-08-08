import os
import tempfile
import unittest

from proxy import ProxyPool


class TestProxyPool(unittest.TestCase):
    def test_round_robin_and_len(self):
        pool = ProxyPool(["http://a:1", "http://b:2"])
        self.assertEqual(len(pool), 2)
        self.assertEqual(pool.next(), "http://a:1")
        self.assertEqual(pool.next(), "http://b:2")
        self.assertEqual(pool.next(), "http://a:1")

    def test_mark_bad_takes_proxy_offline(self):
        pool = ProxyPool(["http://a:1", "http://b:2"])
        pool.mark_bad("http://a:1")
        self.assertEqual(pool.next(), "http://b:2")
        self.assertEqual(pool.next(), "http://b:2")
        pool.mark_bad("http://b:2")
        self.assertIsNone(pool.next())
        self.assertEqual(pool.alive(), [])

    def test_mark_ok_recovers_health(self):
        pool = ProxyPool(["http://a:1"])
        pool.mark_bad("http://a:1")
        self.assertIsNone(pool.next())
        pool.mark_ok("http://a:1")
        self.assertEqual(pool.next(), "http://a:1")

    def test_load_from_file_skips_comments_and_blanks(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write("# comment\nhttp://c:3\n\nhttp://d:4\n")
            path = f.name
        try:
            pool = ProxyPool(filepath=path)
            self.assertEqual(len(pool), 2)
            self.assertIn("http://d:4", pool.alive())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
