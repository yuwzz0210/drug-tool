# 数据字典 v1.0（药品域三层模型 + 清洗规则）

> 制定日期：2026-09-02；状态：已落地（drug_molecule 表 + normalize.py 清洗管道 + 测试）
> 解决：双轨 schema 分裂、缺品种聚合层、字段污染、全角/罗马/分隔符混乱。

## 1. 三层实体模型

```
drug_molecule（品种/分子层）── 主键：规范通用名（清洗后，不含剂型/盐基/标识）
  └── drug_product（厂家×通用名+剂型 注册产品层）── 业务键：通用名+剂型+规格+厂家
        └── drug_registration（批准文号层）── 唯一键：批准文号
```

横向对比查 molecule 层；一品种一页从 molecule 展开到 product/registration。

## 2. 字段字典（molecule 层）

| 字段 | 定义 | 类型 | 必填 | 权威来源 | 更新方式 |
| --- | --- | --- | --- | --- | --- |
| molecule_id | 主键 | int | 是 | 系统 | 自动 |
| generic_name | 规范通用名（清洗后） | str | 是 | NMPA+人工 | 自动聚合+人工 |
| atc_code | ATC 编码 | str | 否 | 人工/第三方 | 人工 |
| drug_type | 药品类别（化学/生物/中成药…） | enum | 否 | NMPA | 自动 |
| mechanism_summary | 作用机制摘要 | text | 否 | 说明书/人工 | 人工(P3) |
| is_verified | 是否人工核验 | bool | 是 | — | 人工 |

## 3. 字段字典（product / registration 层，沿用现有 drug_product/drug_registration）

| 字段 | 定义 | 必填 | 来源 | 说明 |
| --- | --- | --- | --- | --- |
| generic_name | 通用名（保留原始写法） | 是 | NMPA/人工 | 清洗用 molecule_id 聚合 |
| dosage_form / specification | 剂型/规格 | 否(目标100%) | NMPA 详情 | 补全进行中 |
| manufacturer_norm | 厂家（已拆分+笔误修正） | 是 | NMPA | 多厂家用数组/多行 |
| approval_number | 批准文号 | 是 | NMPA | 唯一键 |
| registration_date / holder | 批准日期/上市许可持有人 | 否 | NMPA 详情 | 补全进行中 |
| is_verified | 人工核验标记 | 是 | — | 人工 |

## 4. 清洗规则清单（normalize.py，全部有测试）

| 规则 | 作用 | 示例 |
| --- | --- | --- |
| to_half_width | 全角→半角 | （）→()、；→; |
| norm_roman | 罗马数字归一 | Ⅰ→I、ⅱ→II |
| strip_class_markers | 剥离分类标识 | 利拉鲁肽（H）→利拉鲁肽 |
| strip_dosage_form | 剥离剂型 | 乌帕替尼缓释片→乌帕替尼缓释 |
| strip_salt | 剥离盐基 | 甲磺酸奥希替尼→奥希替尼 |
| molecule_key | 组合为聚合键 | 二甲双胍恩格列净片（Ⅰ）→二甲双胍恩格列净 |
| split_manufacturers | 厂家拆分+角色剥离+笔误修正 | 原液/制剂生产企业；序号（1）（2） |
| KNOWN_CORRECTIONS | 已知笔误映射 | 国药集国国瑞→国药集团国瑞 |

## 5. 数据质量门禁（CI）
- schema 校验：三层表结构、必填字段。
- 枚举校验：drug_type、医保类别等锁死枚举。
- 重复检测：molecule 键唯一、批准文号唯一。
- 完备率报表：剂型/规格/医保/批准日期填充率（目标 ≥90%）。
- 清洗回归：normalize 规则全部单测，防回退。

## 6. 数据流向（唯一主库）
```
爬虫/人工 → 原始层 → 清洗层(normalize.py) → 规范层(drug_molecule/product/registration)
    → data/drugs.json（快照，git 版本管理 = 唯一可信源）
    → 前端展示（localStorage 仅作缓存）
```
人工网页编辑：导出 JSON → tools/import_drugs.py 合并回库 → 提交仓库（写回机制，待做提交接口）。

## 7. 价格层 price_history（2026-09-02 新增）

| 字段 | 定义 | 必填 | 说明 |
| --- | --- | --- | --- |
| product_id | 关联注册产品 | 是 | 价格挂在 product（厂家×规格）层 |
| price_type | 价格类型 | 是 | 枚举：挂网/中标/集采中选/零售 |
| price | 价格 | 是 | 数值 |
| unit | 计价单位 | 否 | 如 元/盒、元/支 |
| effective_date / expire_date | 生效/失效 | 否 | 支持价格时间线 |
| source_url / reviewed_at / reviewed_by | 来源与核查 | 否 | 留痕 |

唯一键：`(product_id, price_type, effective_date, price)`；录入入口：tools/import_price_market.py。

## 8. 市场层 drug_market（2026-09-02 新增）

| 字段 | 定义 | 说明 |
| --- | --- | --- |
| molecule_id | 关联品种分子 | 市场按品种聚合 |
| region | 区域 | 全国 / 湖南… |
| sales_year | 年份 | 唯一键之一 |
| patient_count / diagnosis_rate / prescription_penetration | 患者池/确诊率/处方渗透率 | 估算输入 |
| annual_sales | 年销售额 | 文本（亿元/口径） |
| formula | 计算公式/口径 | 留痕可追溯 |
| confidence | 置信度 | 枚举：高/中/低 |
| source / estimated_date / reviewed_at | 来源与估算时间 | 人工估算强制标注 |

唯一键：`(molecule_id, region, sales_year)`；录入入口：tools/import_price_market.py。

## 9. molecule 层新增评分字段（2026-09-02）
guideline_level（指南推荐等级）、route（给药途径）、cold_chain（冷链）、
patent_expiry（专利到期日）、iteration_chain（迭代链）、generation（代次）、
extra_indications（拓展适应症）、reviewed_at（核查时间）。

## 10. 说明书层 drug_leaflet（2026-09-03 新增，步骤3）
一批准文号（CDE 化学药品目录集记录）一条说明书解析结果，PDF 原文 + 关键节落库，便于复核与"一药一页"临床信息展示。

| 字段 | 说明 |
| :--- | :--- |
| product_id | 关联 drug_product（经 drug_registration.approval_number 匹配） |
| approval_number | 批准文号/注册证号（与 CDE 目录集一致） |
| catalog_rid | CDE 目录集记录 idCode（详情页） |
| pdf_url / source_url | CDE 说明书附件直链 / 目录集详情页（溯源） |
| route | 给药途径归一（口服/注射/外用/吸入） |
| storage / cold_chain | 【贮藏】原文 → 冷链归一（常温/阴凉(≤20℃)/冷藏(2~8℃)/冷冻） |
| usage_dosage / indications | 【用法用量】【适应症】原文 |
| leaflet_date | 说明书核准/修订日期（ISO） |
| sections_json / raw_text | 其余关键节 JSON / PDF 全文 |
| fetched_at / updated_at | 采集/更新时间 |

来源：CDE 化学药品目录集（主动公开）；采集器 collectors/cde_leaflets.py，入库 tools/import_cde_leaflets.py。口径：目录集主要收录过评/参比制剂类药品，原研/进口/生物制品缺口由后续"上市药品信息（受理号）"通道补齐。
