# 医药流通政策信息聚合平台 · 爬虫模块

按《医药流通政策信息聚合平台系统开发规格说明书》V1.0 实现的政策爬虫（P0：NMPA 数据源跑通）。
核心功能零第三方依赖（Python 3.9+ 标准库），可离线测试。

## 快速开始

```bash
# 1. 初始化数据库（SQLite，默认 policy_crawler.db）
python main.py init-db

# 2. 离线演示：完整跑通 列表→详情→脱敏→去重入库（用测试夹具，不访问外网）
python main.py crawl --source nmpa --demo

# 3. 线上抓取（默认遵守合规延迟 ≥4s±1s，建议先运行 check-robots）
python main.py check-robots --url https://www.nmpa.gov.cn/xxgk/fgwj/gzwj/gzwjyp/
python main.py crawl --source nmpa --days 7 --limit 50

# 4. 试跑不写库（可加 --no-delay 仅限测试）
python main.py crawl --source nmpa --days 7 --dry-run

# 5. 生成每日 09:00 / 15:00 定时任务
python main.py cron > /etc/cron.d/policy_crawler
```

> 运行 `--demo` 会在项目目录生成 `demo_crawler.db` 与 `logs/`（演示产物，可手动删除）。

## 真实页面验证（2026-08-08）

使用 NMPA「药品法规文件」列表页真实 HTML 校验：18 条政策全部正确解析（标题/日期/URL），
导航噪音（网站声明、联系我们等）已通过「列表目录路径前缀 + 噪音标题」双重过滤排除。
使用真实政策解读详情页校验：正文按「`<div class='text'>` → `id=zoom` → TRS_Editor →
article → content」优先级提取，页头 app 链接噪音已排除；标题/日期/文号提取正确。

## P1：医保局/卫健委解析器 + PDF/OCR

- 新增 `NhsaParser`（国家医保局）与 `NhcParser`（国家卫健委），复用 `GovListParser` 通用列表解析
  （按 `<li>` 提取 + 条目 URL 模式过滤 + 噪音排除 + 合法日期校验），并按来源配置正文容器。
- **已用真实页面收敛选择器**（2026-08-08，54 个测试全绿）：
  - NHSA 政策法规列表（col104）：每页 15 条，索引号（如 2026-02-00018）不会被误判为日期；
  - NHC 政策文件列表（c100048）：每页 24 条，头部导航链接已排除；
  - 两站详情页：标题/日期/文号/发布机构/正文/附件均正确解析（NHSA 取 CMS 标记 + downfile 附件，
    NHC 取 ArticleTitle meta + #xw_box 正文 + PDF 附件）。
- 新增 `extractors.py`：PDF 正文提取（pdfplumber → pypdf → PyPDF2 依次尝试，未安装时优雅返回空）、
  OCR 提取（easyocr，未安装时优雅返回空）；引擎可注入便于测试。
- 管道新增 `enrich_content`：正文过短（<100 字）时尝试 PDF 附件提取与图片 OCR 补充，再执行 PII 脱敏。
- 配置中 NHSA/NHC 列表 URL 已修正为真实栏目地址（原 col40 为「网站声明」，非政策列表）。

## P2：区域数据源注册表 + API 层

### 区域数据源（regional_sources.json）

- `tools/build_regional_sources.py` 把「网址导航」JSON 转换为区域数据源注册表
  （医保局/药监局/卫健委，国家 + 省级，portal 去重，默认 `enabled=False`）：

```bash
python -m tools.build_regional_sources "网址导航_其他标签链接.json" regional_sources.json
```

- 已随项目附带一份由真实导航清单生成的 `regional_sources.json`（290 个区域源），
  `config.load_all_sources()` 自动合并（共 294 个数据源，含 4 个国家级）；
  区域源需逐站用真实列表页校验后手动开启。

### API（规格书第 7 章接口）

- `queries.py`：查询逻辑（列表筛选 keyword/authority/tag/status/date、详情、6 个业务场景专题、统计）；
- `serve.py`：**零依赖 REST 服务**（标准库 http.server），立即可用：

```bash
python main.py serve --db policy_crawler.db --port 8000
# 打开 http://127.0.0.1:8000 直接使用政策浏览前端（API + 页面同源托管）
curl "http://127.0.0.1:8000/api/policies?keyword=集采"
curl http://127.0.0.1:8000/api/policies/1
curl http://127.0.0.1:8000/api/scenarios
curl http://127.0.0.1:8000/api/scenarios/sc_vbp/policies
curl http://127.0.0.1:8000/api/stats/latest
```

- `api_fastapi.py`：FastAPI 薄包装（安装 fastapi/uvicorn 后 `uvicorn api_fastapi:app --port 8000`）；
- 接口已带 CORS（`Access-Control-Allow-Origin: *` + OPTIONS 预检），支持跨域/静态页直接调用；
- 效力状态自动更新：入库时按「标题含废止/失效 → 废止；发布日期晚于今天 → 未生效；否则有效」规则写入；
- `notify.py`：403/异常邮件告警（配置 `SMTP_HOST`/`SMTP_FROM`/`SMTP_TO` 后生效）。

### 前端浏览页（policy-viewer.html）

- 单文件、零依赖、无构建步骤：关键词/机构/状态/日期筛选、6 个业务场景一键联动、政策详情（文号/机构/效力/原文链接/附件）；
- `python main.py serve` 后打开 http://127.0.0.1:8000 即可；也可用 `?api=<地址>` 指定其他 API；
- 未连接 API 时自动降级为内置演示数据并明确标注「离线演示数据」，方便先看效果。

### P3：健康检查 / 监控端点 / 代理池

- `health_check.py`：数据库连通性 + 启用数据源可达性探测（403/412 标记为「可达但被反爬拦截」），
  `--json` 输出便于接入监控；`python health_check.py` 全部通过返回 0；
- `serve.py` 新增 `/api/health`：返回数据库状态、政策数量、启用数据源清单（零依赖监控，Grafana 大盘留作后续）；
- `proxy.py` 代理 IP 池：轮换使用、失败自动下线、成功恢复评分；支持从 `PROXY_LIST` 环境变量或文件加载，
  已接入 `Downloader`（`--proxy` 传入 `ProxyPool` 即生效）。

## 合规基线（已内置）

| 要求 | 实现 |
|---|---|
| robots.txt 检查 | `compliance.py`，按 host 缓存；Disallow 命中即放弃该路径 |
| 请求间隔 ≥4s ±1s | `downloader.py` 随机抖动延迟（`--no-delay` 仅测试用） |
| UA 轮换 | `config.USER_AGENTS` 循环轮换 |
| PII 脱敏 | `sanitize.scrub_pii`：身份证/手机号入库前擦除 |
| 日志留痕 ≥6 个月 | `logging_conf.py` 按日切割，保留 180 天；每次请求记录 URL/状态码/耗时 |
| 403/验证码 | 抛 `PauseSignal`，任务暂停并告警（`SMTP_HOST` 可扩展邮件） |

## 架构

```
main.py (CLI) → compliance (robots) → downloader (UA/延迟/重试/留痕)
             → parsers (按来源注册) → pipeline (脱敏+去重+upsert) → store (SQLite/PostgreSQL)
```

- 数据模型：`models.py`（SQLite schema + 对齐规格书的 PostgreSQL DDL：policies / categories / policy_category / crawler_logs）
- 去重：`source_url` 唯一；已存在则更新 content 与 updated_at（幂等）
- 扩展新数据源：在 `config.SOURCES` 注册 + `parsers.py` 增加解析器

## 配置（环境变量）

| 变量 | 说明 | 默认 |
|---|---|---|
| `CRAWLER_DB` | SQLite 路径 | `policy_crawler.db` |
| `DB_URL` | PostgreSQL 连接串（`--postgres` 时使用） | - |
| `REQUEST_DELAY_MIN/MAX` | 延迟区间（秒） | 4 / 5 |
| `RETRY_TIMES` | 重试次数 | 2 |
| `LOG_RETENTION_DAYS` | 日志保留天数 | 180 |
| `SMTP_HOST` | 告警邮件服务器（预留） | 空 |

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖：HTML 清洗/PII 脱敏/文号提取、robots 解析与缓存、下载器 UA 轮换/重试/403 暂停/请求留痕、
NMPA/NHSA/NHC 列表与详情解析、PDF/OCR 提取器、区域数据源脚本、查询层、REST 服务端到端、
效力状态规则、管道去重/upsert/脱敏/内容增强/运行日志。

## Roadmap（对应规格书后续阶段）

- P1：增加医保局/卫健委数据源解析器；PDF 附件提取（pdfplumber）；OCR（PaddleOCR/EasyOCR）；
- P2：API 与业务场景专题（已完成）；前端浏览页 `policy-viewer.html`（已完成，同源托管）；
- P3：健康检查 `health_check.py`、`/api/health` 监控端点、代理 IP 池 `proxy.py`（已完成）；
  监控大盘（Grafana）与自动化部署（Docker/云主机）待做；
- 可选切换 Scrapy（下载器接口已解耦，可替换实现）。

## 免责声明

仅抓取国家及地方药监局、医保局、卫健委等官方**主动公开**政策页面；严格遵守 robots.txt 与访问频率限制，
抓取内容仅供内部查阅，版权归原发布机构所有。
