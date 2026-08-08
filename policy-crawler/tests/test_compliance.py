import unittest

from compliance import RobotsChecker


ROBOTS = """User-agent: *
Disallow: /xxgk/search
Disallow: /data
Allow: /xxgk/fgwj
"""


class FakeFetcher:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def __call__(self, url, ua=None):
        self.calls += 1
        return 200, self.text


class TestRobotsChecker(unittest.TestCase):
    def setUp(self):
        self.checker = RobotsChecker(fetcher=FakeFetcher(ROBOTS))

    def test_allowed_public_path(self):
        self.assertTrue(self.checker.allowed("https://www.nmpa.gov.cn/xxgk/fgwj/gzwj/gzwjyp/a.html"))

    def test_disallowed_path(self):
        self.assertFalse(self.checker.allowed("https://www.nmpa.gov.cn/data/abc.html"))
        self.assertFalse(self.checker.allowed("https://www.nmpa.gov.cn/xxgk/search?q=1"))

    def test_allow_overrides_disallow(self):
        self.assertTrue(self.checker.allowed("https://www.nmpa.gov.cn/xxgk/fgwj/list.html"))

    def test_robots_cached_per_host(self):
        self.checker.allowed("https://www.nmpa.gov.cn/a.html")
        self.checker.allowed("https://www.nmpa.gov.cn/b.html")
        self.assertEqual(self.checker._fetcher.calls, 1)


if __name__ == "__main__":
    unittest.main()
