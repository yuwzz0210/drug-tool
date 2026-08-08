# 医药流通政策信息聚合平台（drug-tool）

按疾病领域追踪药品迭代数据、辅助品种评估决策的工具，配套医药流通政策每日自动抓取。

## 网站

- 首页：https://yuwzz0210.github.io/drug-tool/
- 「政策追踪 → 全网政策」：读取 `data/policies.json`，由 GitHub Actions 每日自动抓取 NMPA / NHSA / NHC 政策并更新。

## 目录结构

```text
├── index.html              # 网站（单文件 SPA：一药一页 / 一策一页 / 政策追踪 / 数据管理）
├── data/policies.json      # 每日自动更新的政策数据（网站前端读取）
├── policy-crawler/         # 爬虫系统（零依赖 Python 3.9+，TDD，74 个测试）
│   ├── main.py             # CLI：crawl / serve / check-robots / init-db / cron
│   ├── parsers.py          # NMPA / NHSA / NHC 解析器（真实页面收敛）
│   ├── serve.py            # 零依赖 REST API + 前端托管（python main.py serve）
│   ├── policy-viewer.html  # 政策浏览前端（API 或离线演示数据）
│   ├── health_check.py     # 数据库 + 数据源健康检查
│   ├── proxy.py            # 代理 IP 池（防封禁）
│   └── tests/              # 74 个单元测试与真实页面 fixtures
├── docs/                   # 迭代发布说明与方案文档
└── .github/workflows/daily-crawl.yml  # 每日 08:00 / 20:00（北京时间）自动抓取并提交
```

## 每日自动更新（GitHub Actions）

工作流 `.github/workflows/daily-crawl.yml`：

1. 每天北京时间 08:00 和 20:00 触发（也可在 Actions 页面手动触发 `workflow_dispatch`）；
2. 运行 `policy-crawler/main.py crawl --source nmpa|nhsa|nhc --days 1 --output data/policies.json`；
3. 按 URL 增量合并去重后写回 `data/policies.json`；
4. 有变更时自动提交推送（`[skip ci]` 避免循环触发），GitHub Pages 随即更新网站。

## 本地使用

```powershell
cd policy-crawler
python -m unittest discover -s tests -q   # 74 个测试
python main.py crawl --source nmpa --days 7 --output ..\data\policies.json
python main.py serve --db policy_crawler.db --port 8000   # http://127.0.0.1:8000
python health_check.py
```

## 合规基线

robots.txt 检查、请求间隔 ≥4 秒、UA 轮换、PII 脱敏、请求留痕 180 天；仅抓取政府主动公开政策。
