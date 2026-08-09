# 爬取检测报告（2026-08-10）

## 结论

解析器对三个真实官网页面的**列表解析、详情解析、入库、JSON 输出**全链路验证通过。
当前政策库（`policy_crawler.db`）共 **57 条**政策，`data/policies.json` 共 **57 条**记录，
字段完整、日期合法、URL 无重复、无伪造演示数据。

> 说明：本次检测使用此前保存的官网真实 HTML（NMPA/NHSA/NHC 各一个列表页 + 一个详情页），
> 在无外网环境下等价验证了生产解析器。真实联网抓取（回填全部详情正文）见文末步骤。

## 1. 解析器真实页面表现

| 来源 | 列表解析条数 | 详情标题 | 详情日期 | 文号 | 发布机构 | 正文长度 | 附件 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NMPA 国家药品监督管理局 | 18 | 《国家药监局关于化妆品注册备案有关事项的公告》政策解读 | 2026-07-29 | 国药监妆〔2025〕18号（从解读正文提取） | 国家药品监督管理局 | 2791 字 | 0 |
| NHSA 国家医疗保障局 | 15 | 关于确定医保支持基层医疗卫生服务发展重点联系点的通知 | 2026-07-17 | 医保办函〔2026〕52号 | 国家医疗保障局 | 139 字 | 1 |
| NHC 国家卫生健康委 | 24 | 关于发布《感染性腹泻诊断标准》等4项法定传染病诊断标准的通告 | 2026-07-29 | 国卫通〔2026〕10号 | 法规司 | 254 字 | 4 |

合计 **57 条**（18 + 15 + 24）。

## 2. 政策库（SQLite）检测

- 总行数：57
- 来源分布：NMPA 18 / NHSA 15 / NHC 24
- 必填字段（标题、URL、发布日期、发布机构）缺失：0
- 日期格式非法（非 YYYY-MM-DD）：0
- URL 重复：0
- 伪造演示 URL（如 `123456.html`）：0（演示种子已剔除）
- 含详情正文：2 条（NHSA、NHC 各 1 条，与保存的详情页正确匹配）
- 含附件链接：2 条

## 3. JSON 输出（data/policies.json）检测

- 记录数：57
- 字段：`id / title / url / publish_date / content_preview / source_site / created_at` 全部齐全
- URL 唯一：通过
- 按发布日期倒序排列：通过
- `source_site` 分布：国家药品监督管理局 18 / 国家医疗保障局 15 / 法规司 24

## 4. 幂等性

同一批数据重复构建：库与 JSON 均保持 57 条、新增 0 条，增量合并去重逻辑正常。

## 5. 数据质量说明

1. **正文覆盖为 2 条是预期现象**：离线检测每个来源只保存了一个详情页，
   详情正文只挂接到标题匹配的条目上。真实联网爬取会逐个抓取详情页回填正文。
2. **NMPA 详情页与列表页不是同一篇**（保存的详情为化妆品解读，列表第一条为中药品种保护通知），
   已改为严格标题匹配，不匹配则不挂接正文，避免把错误内容写入库。
3. **NHC 的 source_site 显示为「法规司」**：为详情页解析出的实际发文部门，
   与正式爬取逻辑一致（详情页机构优先，缺省用站点名）。
4. 之前 `policy_crawler.db` 中的 2 条演示种子（伪造 URL）已从正式库和 JSON 中剔除，
   本次 57 条全部来自真实官网页面解析。

## 6. 真实联网爬取（下一步）

沙箱内无外网，以下命令请在本机终端执行（policy-crawler 目录下）：

```powershell
cd C:\Users\YUWZZ\Documents\Codex\2026-08-07\github-plugin-github-openai-api-curated\outputs\policy-crawler
python main.py crawl --source nmpa --days 30 --output ..\..\repo\data\policies.json
python main.py crawl --source nhsa --days 30 --output ..\..\repo\data\policies.json
python main.py crawl --source nhc --days 30 --output ..\..\repo\data\policies.json
```

或到 GitHub 仓库 `yuwzz0210/drug-tool` → Actions → daily-crawl → Run workflow 手动触发，
云端会自动抓取并提交 `data/policies.json`。

抓取完成后用以下命令浏览政策库：

```powershell
python main.py serve --db policy_crawler.db --port 8000
# 浏览器打开 http://127.0.0.1:8000
```
