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
