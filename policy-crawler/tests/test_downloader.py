import unittest

from downloader import Downloader, PauseSignal
from proxy import ProxyPool


class RecordingFetcher:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.calls = []
        self.index = 0

    def __call__(self, url, ua=None):
        self.calls.append((url, ua))
        r = self.responses[self.index] if self.index < len(self.responses) else self.responses[-1]
        self.index += 1
        if isinstance(r, Exception):
            raise r
        return r


class TestDownloader(unittest.TestCase):
    def test_ua_rotation_cycles(self):
        fetcher = RecordingFetcher([(200, "ok")])
        d = Downloader(ua_list=["UA-A", "UA-B"], delay_range=(0, 0), retries=0, fetcher=fetcher)
        for _ in range(3):
            d.fetch("https://example.com/a")
        uas = [c[1] for c in fetcher.calls]
        self.assertEqual(uas, ["UA-A", "UA-B", "UA-A"])

    def test_retry_then_success(self):
        fetcher = RecordingFetcher([OSError("timeout"), (200, "ok")])
        d = Downloader(ua_list=["UA"], delay_range=(0, 0), retries=2, fetcher=fetcher)
        status, body = d.fetch("https://example.com/a")
        self.assertEqual(status, 200)
        self.assertEqual(body, "ok")
        self.assertEqual(len(fetcher.calls), 2)

    def test_403_raises_pause_signal(self):
        fetcher = RecordingFetcher([(403, "forbidden")])
        d = Downloader(ua_list=["UA"], delay_range=(0, 0), retries=0, fetcher=fetcher)
        with self.assertRaises(PauseSignal):
            d.fetch("https://example.com/a")

    def test_request_logging(self):
        records = []
        fetcher = RecordingFetcher([(200, "ok")])
        d = Downloader(
            ua_list=["UA"], delay_range=(0, 0), retries=0, fetcher=fetcher,
            on_request=lambda url, status, elapsed: records.append((url, status, elapsed)),
        )
        d.fetch("https://example.com/a")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], "https://example.com/a")
        self.assertEqual(records[0][1], 200)
        self.assertGreaterEqual(records[0][2], 0)

    def test_proxy_pool_used_on_success(self):
        used = []

        class ProxyDownloader(Downloader):
            def _proxied_fetch(self, url, ua, proxy):
                used.append(proxy)
                return 200, "proxied"

        pool = ProxyPool(["http://p1:8080"])
        d = ProxyDownloader(ua_list=["UA"], delay_range=(0, 0), retries=0, proxy_pool=pool)
        status, body = d.fetch("https://example.com/a")
        self.assertEqual((status, body), (200, "proxied"))
        self.assertEqual(used, ["http://p1:8080"])
        self.assertEqual(pool.alive(), ["http://p1:8080"])

    def test_proxy_failure_marks_bad_and_falls_back(self):
        class FailingProxyDownloader(Downloader):
            def _proxied_fetch(self, url, ua, proxy):
                raise OSError("proxy unreachable")

        pool = ProxyPool(["http://p1:8080"])
        fetcher = RecordingFetcher([(200, "direct")])
        d = FailingProxyDownloader(
            ua_list=["UA"], delay_range=(0, 0), retries=1,
            fetcher=fetcher, proxy_pool=pool,
        )
        status, body = d.fetch("https://example.com/a")
        self.assertEqual((status, body), (200, "direct"))
        self.assertEqual(pool.alive(), [])


if __name__ == "__main__":
    unittest.main()
