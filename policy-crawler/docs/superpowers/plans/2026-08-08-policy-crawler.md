# 医药流通政策爬虫 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按《医药流通政策信息聚合平台系统开发规格说明书》实现一个合规、可离线测试的 Python 政策爬虫（P0：NMPA 数据源跑通）。

**Architecture:** 单进程、stdlib-only 的分层管道：compliance（robots 检查）→ downloader（UA 轮换/延迟/重试/403 暂停）→ parser（按来源注册的解析器）→ pipeline（source_url 去重 + upsert 入库 + 运行日志）。存储抽象为 SQLite（默认、零依赖）/ PostgreSQL（可选 psycopg2），表结构对齐规格书。

**Tech Stack:** Python 3.9+ 标准库（urllib / html.parser / logging / sqlite3 / unittest）；可选依赖 requests、lxml、psycopg2-binary。

---

## 文件结构

```
outputs/policy-crawler/
├── README.md
├── requirements.txt
├── config.py            # 数据源注册、UA 列表、延迟/重试/日志保留配置
├── logging_conf.py      # 按日切割日志、保留 180 天
├── sanitize.py          # HTML 清洗、PII 脱敏、发文字号提取
├── compliance.py        # robots.txt 解析与路径权限判断
├── downloader.py        # 请求：UA 轮换、≥4s±1s 延迟、重试、403 暂停信号、请求留痕
├── parser.py            # BaseParser + NmpaParser + PARSERS 注册表
├── models.py            # Policy dataclass + SQLite schema + PostgreSQL DDL
├── store.py             # Store 抽象 + SqliteStore + PostgresStore(可选)
├── pipeline.py          # 去重 + upsert + 运行统计
├── scheduler.py         # 每日 09:00/15:00 crontab 生成
├── main.py              # CLI：crawl / check-robots / init-db / cron
├── docs/superpowers/plans/2026-08-08-policy-crawler.md
└── tests/
    ├── __init__.py
    ├── fixtures/nmpa_list.html
    ├── fixtures/nmpa_detail.html
    ├── test_sanitize.py
    ├── test_compliance.py
    ├── test_parser.py
    ├── test_downloader.py
    └── test_pipeline.py
```

---

## Task 1: 数据清洗与脱敏（sanitize.py）

**Files:** `sanitize.py`、`tests/test_sanitize.py`

- [ ] **Step 1: 写失败测试**（clean_html_text 保留段落、scrub_pii 擦除身份证/手机号、extract_doc_number 提取发文字号）
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 实现最小代码**
- [ ] **Step 4: 运行测试确认通过**

## Task 2: robots 合规检查（compliance.py）

**Files:** `compliance.py`、`tests/test_compliance.py`

- [ ] **Step 1: 写失败测试**（解析 robots、按 User-agent 与 Disallow 判断 allowed）
- [ ] **Step 2-4: 红绿循环**

## Task 3: 下载器（downloader.py）

**Files:** `config.py`、`logging_conf.py`、`downloader.py`、`tests/test_downloader.py`

- [ ] **Step 1: 写失败测试**（UA 轮换、重试、403 暂停、请求留痕、延迟 0 注入）
- [ ] **Step 2-4: 红绿循环**

## Task 4: 解析器（parser.py）

**Files:** `parser.py`、`tests/fixtures/*.html`、`tests/test_parser.py`

- [ ] **Step 1: 写失败测试**（NMPA 列表页 2 条 → url/title/date；详情页 → title/date/doc_number/content）
- [ ] **Step 2-4: 红绿循环**

## Task 5: 存储与管道（models.py / store.py / pipeline.py）

**Files:** `models.py`、`store.py`、`pipeline.py`、`tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试**（SQLite 建表、source_url 去重、第二次运行 new_added=0、upsert 更新 content、crawler_logs 记录）
- [ ] **Step 2-4: 红绿循环**

## Task 6: CLI 与调度（main.py / scheduler.py）

**Files:** `main.py`、`scheduler.py`、`README.md`

- [ ] **Step 1: 实现**（crawl/check-robots/init-db/cron 子命令；crontab 生成）
- [ ] **Step 2: 端到端验证**（`python main.py init-db` + 本地 fixture dry-run + 全量测试）
- [ ] **Step 3: 可选线上冒烟**（单次请求 NMPA 列表页，遵守延迟）

## 规格覆盖自查

- 2.2 合规基线：robots（Task2）、≥4s±1s 延迟（Task3）、UA 轮换（Task3）、PII 脱敏（Task1）、日志留痕 6 个月（Task3/logging_conf）
- 5.2 下载器：延迟/重试/403 暂停（Task3）
- 5.3 解析器：标题/日期/文号/正文（Task4）；PDF/OCR 为扩展占位（README 说明）
- 5.4 管道：source_url 幂等 upsert（Task5）
- 4 数据模型：policies/categories/policy_category/crawler_logs（Task5，SQLite + Postgres DDL）
- 5.1 调度：每日 09:00/15:00（Task6）
- 8 运维：环境变量、日志按日切割 30 天（规格）/本项目 180 天（合规留痕），health_check 说明在 README
- 未实现（后续阶段）：FastAPI 接口、Vue 前端、Scrapy/Selenium、OCR、代理池（README 标注 roadmap）

---

## P1 追加：医保局/卫健委解析器 + PDF/OCR

### Task 7: 数据源解析器（nhsa / nhc）

**Files:** `parsers.py`、`config.py`、`tests/fixtures/nhsa_*.html`、`tests/fixtures/nhc_*.html`、`tests/test_parser.py`

- [x] **Step 1: 写失败测试**（NHSA/NHC 列表按 li 解析 + 各自 keep_paths 过滤；详情正文按各自内容容器提取）
- [x] **Step 2-4: 红绿循环**（实现 `GovListParser` 基类，`NhsaParser`/`NhcParser` 复用 + 每源内容容器模式）
- [x] **Step 5: 附件链接提取**（详情页 .pdf/.doc/.docx/.txt/downfile.jsp 链接入 `attachment_links`）

### Task 8: PDF / OCR 提取器（extractors.py）

**Files:** `extractors.py`、`tests/test_extractors.py`

- [x] **Step 1: 写失败测试**（未装库时优雅返回空；注入假引擎可提取文本；OCR 同理）
- [x] **Step 2-4: 红绿循环**

### Task 9: 管道内容增强（pipeline.py）

**Files:** `pipeline.py`、`tests/test_pipeline.py`

- [x] **Step 1: 写失败测试**（正文过短且有 PDF 附件 → 提取追加；仍过短且有本地图片 → OCR）
- [x] **Step 2-4: 红绿循环**（`enrich_content` 支持注入 PDF/OCR 引擎与 URL 获取函数）

### Task 10: 真实页面待校验清单（交付物）

- [x] **Step 1: 输出需要用户提供的网址/HTML 清单**（NHSA/NHC 列表页 + 详情页各一）
- [x] **Step 2: 全量测试 + README 更新**（54 个测试全绿；选择器已按真实页面收敛）

### P1 覆盖自查
- 规格 P1：「增加医保局、卫健委数据源」→ Task7；「完善解析器（PDF/OCR）」→ Task8/9
- 合规基线不变（下载器复用）
- 说明：NHSA/NHC 解析器已用真实页面收敛（列表 col104/c100048 + 详情 CMS 标记 / #xw_box）

---

## P2 追加：区域数据源注册表 + API 层

### Task 11: 区域数据源脚本（tools/build_regional_sources.py）

**Files:** `tools/build_regional_sources.py`、`config.py`、`tests/test_regional_sources.py`

- [x] **Step 1: 写失败测试**（导航 JSON 样本 → 生成国家+省级条目，parser 按类别映射，enabled=False，portal 去重）
- [x] **Step 2-4: 红绿循环**
- [x] **Step 5: config 支持合并 regional_sources.json**（290 个源，默认 enabled=False）

### Task 12: API 查询层（queries.py）+ 零依赖 REST（serve.py）+ FastAPI 包装

**Files:** `queries.py`、`serve.py`、`api_fastapi.py`、`tests/test_queries.py`

- [x] **Step 1: 写失败测试**（列表筛选 keyword/authority/date、详情、场景专题、统计、状态标签规则）
- [x] **Step 2-4: 红绿循环**
- [x] **Step 5: serve.py 本地 REST 端到端测试（httptest）**
- [x] **Step 6: FastAPI 薄包装（需安装 fastapi/uvicorn，语法检查）**

### Task 13: 状态标签自动更新 + 邮件告警（轻量）

**Files:** `validity.py`（或并入 queries）、`notify.py`、`tests/test_validity.py`

- [x] **Step 1: 写失败测试**（未生效/有效/废止规则）
- [x] **Step 2-4: 红绿循环**

### Task 14: 前端浏览页 + 同源托管（P2「接口和前端」落地）

**Files:** `policy-viewer.html`、`serve.py`、`tests/test_serve.py`

- [x] **Step 1: 写失败测试**（API 响应带 CORS 头、OPTIONS 预检 204、非法 page/size 参数回落、根路径返回前端页）
- [x] **Step 2-4: 红绿循环**
- [x] **Step 5: 浏览器渲染验证**（Edge 无头截图 + 像素抽样：深色头部/白色面板/内容多样性，离线演示降级正常）

### P2 覆盖自查
- 规格 P2：「接入业务场景逻辑」→ queries.SCENARIOS + /api/scenarios/*；「配置定时任务与邮件告警」→ scheduler + notify；
  「设计状态标签自动更新逻辑」→ update_validity
- 规格 7 章接口：/api/policies、/api/policies/{id}、/api/scenarios、/api/scenarios/{id}/policies、/api/stats/latest 全部实现
- 前端：`python main.py serve` 后打开 http://127.0.0.1:8000 即用（API + 前端同源托管，CORS 兼容 file:// 与跨域调用）

---

## P3 追加：健康检查 + 监控端点 + 代理池 + JSON 站点产物

### Task 15: JSON 站点产物（main.py --output / save_to_json）

- [x] **Step 1: 写失败测试**（字段 schema、增量合并去重、稳定 id、损坏文件重建、CLI 输出）
- [x] **Step 2-4: 红绿循环**（`save_to_json` 按 url 合并，publish_date 倒序；`--output` 默认 data/policies.json）

### Task 16: GitHub Actions 每日自动抓取（daily-crawl.yml）

- [x] **Step 1: 编写工作流**（cron UTC 0/12 点、workflow_dispatch、ubuntu + Python 3.11、单源失败不中断、提交 [skip ci]）
- [x] **Step 2: 产物校验步骤**（JSON 数组 + 必填字段断言）

### Task 17: 健康检查与监控（health_check.py + /api/health）

- [x] **Step 1: 写失败测试**（数据库连通/损坏、源可达/403 标记、汇总报告、/api/health 端点）
- [x] **Step 2-4: 红绿循环**

### Task 18: 代理 IP 池（proxy.py + Downloader 接线）

- [x] **Step 1: 写失败测试**（轮换、下线、恢复、文件加载、下载器代理成功/失败回退）
- [x] **Step 2-4: 红绿循环**

### P3 覆盖自查
- 规格 P3：「增加代理IP池」→ proxy.py（PROXY_LIST 或文件加载，已接入下载器）；
  「监控大盘（Grafana）」→ /api/health + 日志留痕已具备数据源，Grafana 可视化留待部署阶段；
  「高可用防封禁」→ 合规延迟 + UA 轮换 + 代理池 + 403 暂停告警
