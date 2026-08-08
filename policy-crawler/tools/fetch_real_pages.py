# -*- coding: utf-8 -*-
"""在用户本机下载 NHSA/NHC 真实列表页 + 详情页，供解析器选择器收敛使用。

用法（在 policy-crawler 目录下）:
    python tools/fetch_real_pages.py

输出:
    work/nhsa-real/list.html
    work/nhsa-real/detail.html
    work/nhc-real/list.html
    work/nhc-real/detail.html

说明:
    - 本脚本在沙箱内无法联网（网络被拦截），需要在用户自己电脑上运行。
    - 遵守合规基线：请求前检查 robots.txt，请求间隔 4-5 秒，轮换浏览器 UA。
    - 若某站点返回 412/403 或列表页不含条目链接（JS 渲染），会给出提示，
      此时请用浏览器另存页面（Ctrl+S，网页，全部）。
"""

import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# 让脚本从 policy-crawler 根目录导入 config
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import config  # noqa: E402


WORK_ROOT = os.path.join(os.path.dirname(ROOT), "work")

TARGETS = {
    "nhsa": {
        "list_url": config.SOURCES["nhsa"]["list_url"],
        "out_dir": os.path.join(WORK_ROOT, "nhsa-real"),
        "link_re": re.compile(r'href=["\']([^"\']*?/art/\d{4}/\d+/art_\d+_\d+\.html)["\']', re.I),
    },
    "nhc": {
        "list_url": config.SOURCES["nhc"]["list_url"],
        "out_dir": os.path.join(WORK_ROOT, "nhc-real"),
        "link_re": re.compile(r'href=["\']([^"\']*?/fzs/[^"\']*?/20\d{6}/[^"\']+\.shtml)["\']', re.I),
    },
}


def _fetch(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, resp.read()


def robots_allows(url):
    """简化版 robots 检查：读取主机 robots.txt，按 User-agent: * 的 Disallow 判断。"""
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        _, body = _fetch(robots_url, config.USER_AGENTS[0])
    except Exception:
        return True  # 拿不到 robots.txt 时不阻断
    text = body.decode("utf-8", "ignore")
    disallowed = []
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip().lower()
            if agent not in ("*", "codex", "python-urllib"):
                continue
        if line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                disallowed.append(path)
    path = parsed.path or "/"
    return not any(path.startswith(d) for d in disallowed)


def _abs_link(base_url, href):
    return urllib.parse.urljoin(base_url, href)


def main():
    random.seed()
    for name, cfg in TARGETS.items():
        print(f"\n=== {name}: {cfg['list_url']}")
        if not robots_allows(cfg["list_url"]):
            print("robots.txt 禁止抓取该栏目，跳过（请改用浏览器另存）。")
            continue
        os.makedirs(cfg["out_dir"], exist_ok=True)
        ua = random.choice(config.USER_AGENTS)
        try:
            status, body = _fetch(cfg["list_url"], ua)
        except urllib.error.HTTPError as e:
            print(f"列表页 HTTP {e.code}，被站点拦截，请改用浏览器另存。")
            continue
        except Exception as e:
            print(f"列表页下载失败: {e}")
            continue
        print(f"列表页 OK ({status}, {len(body)} bytes)")
        list_path = os.path.join(cfg["out_dir"], "list.html")
        with open(list_path, "wb") as f:
            f.write(body)
        print(f"已保存: {list_path}")

        text = body.decode("utf-8", "ignore")
        links = list(dict.fromkeys(cfg["link_re"].findall(text)))
        if not links:
            print("列表页未解析出条目链接（可能是 JS 动态加载），请浏览器打开列表页 Ctrl+S 另存覆盖 list.html，并另存一个详情页为 detail.html。")
            continue
        detail_url = _abs_link(cfg["list_url"], links[0])
        print(f"详情页: {detail_url}")
        time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))
        try:
            status, dbody = _fetch(detail_url, ua)
        except urllib.error.HTTPError as e:
            print(f"详情页 HTTP {e.code}，请浏览器另存详情页为 detail.html。")
            continue
        except Exception as e:
            print(f"详情页下载失败: {e}")
            continue
        print(f"详情页 OK ({status}, {len(dbody)} bytes)")
        detail_path = os.path.join(cfg["out_dir"], "detail.html")
        with open(detail_path, "wb") as f:
            f.write(dbody)
        print(f"已保存: {detail_path}")
    print("\n完成。把文件路径发给我即可，或直接告诉我已放到 work/nhsa-real 与 work/nhc-real。" )


if __name__ == "__main__":
    main()
