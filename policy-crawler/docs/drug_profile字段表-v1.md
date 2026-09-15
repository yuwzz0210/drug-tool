# drug_profile 字段表 v1（一药一页数据契约）

生成日期：2026-09-14 ｜ 状态：设计稿（前端展示需求 → 数据契约）

## 0. 粒度与口径
- 粒度：**一行 = 一个批准文号（注册规格）**，字段 `approval_number` 为业务唯一键；
  `product_id` 为物理主键（稳定内部 ID，文号可变更）。
- 分子层字段（ATC/机制/迭代链/指南等级）来自 molecule，按 product.molecule_id 关联；
  横向对比使用单独的 molecule 聚合（同病种/同分子系）查询。
- “最新值”口径统一在视图内定义，禁止前端自行取数：
  - 医保：当前有效目录版本（`is_current=1` 且目录最新），默认 `region='国家'`，可携省版列表；
  - 价格：按 `price_type` 取各自最新 `effective_date`（挂网/集采/支付标准）并携带地区与批次；
  - 说明书：取 `updated_at` 最新一条 leaflet；
  - 集采：聚合 `procurement_result` 全批次（数组）。
- 溯源：每段数据附 `source_url` 或 `source`；派生字段标注 algorithm 版本。

## 1. 身份/基础层
| 展示项 | 字段名 | 类型 | 来源/计算 | 现状 |
| :--- | :--- | :--- | :--- | :--- |
| 批准文号 | approval_number | text(UNIQUE) | drug_registration | ✅ |
| 通用名 | generic_name | text | drug_product | ✅ |
| 商品名 | trade_name | text | drug_product | ◐ 106/1206 |
| 生产厂家 | manufacturer | text | drug_product.manufacturer_norm | ✅ |
| 上市许可持有人 | holder | text | drug_registration.holder | ◐ |
| 剂型 | dosage_form | text | drug_product | ◐ 593/1206 |
| 规格 | specification | text | drug_product | ◐ 593/1206 |
| 注册分类 | registration_class | text | 新字段（NMPA/CDE 受理信息） | ✗ |
| 获批日期 | approval_date | date | drug_registration.registration_date | ◐ 881 |
| 药监状态 | approval_status | text | NMPA/会员源（有效/注销…） | ✗ 新列 |
| 药品本位码 | national_drug_code | text | NMPA/会员源（identity 辅助） | ✗ 新列 |
| 国产/进口 | origin_type | text | 文号前缀派生（H/Z vs J/S） | ◐ 派生 |
| ATC | atc_code | text | molecule / CDE 目录集 | ✗ 0/85 |
| 是否OTC | is_otc | bool | drug_product | ◐ |

## 2. 临床/说明书层
| 展示项 | 字段名 | 类型 | 来源/计算 | 现状 |
| :--- | :--- | :--- | :--- | :--- |
| 获批适应症 | indications[] | text[] | drug_indication | ◐ 495 条 |
| 拓展适应症 | extra_indications | text | molecule.extra_indications | ✗ |
| 作用机制 | mechanism_summary | text | molecule / leaflet【药理毒理】 | ◐ 472 |
| 机制(大白话) | mech_plain | text | 人工录入 | ✗ |
| 适应症(大白话) | ind_plain | text | 人工录入 | ✗ |
| 沟通要点 | talking_points | text | 人工录入 | ✗ |
| 给药途径 | route | text | molecule.route / leaflet | ◐ 4/85 |
| 冷链要求 | cold_chain | text | molecule / leaflet【贮藏】 | ◐ |
| 用法用量 | usage_dosage | text | drug_leaflet | ◐ 415 |
| 说明书链接 | leaflet_url | text | drug_product.package_insert_url | ◐ 498 |
| 说明书修订日 | leaflet_date | date | drug_leaflet | ◐ |
| 指南推荐等级 | guideline_level | text | molecule（指南数据/人工） | ✗ 0/85 |
| 代际 | generation | text | molecule | ✗ |
| 迭代链 | iteration_chain | text | molecule | ✗ |
| 前代品种 | predecessor | text | molecule.iteration_chain 派生/人工 | ✗ |
| 生命周期 | lifecycle_stage | enum | 派生：专利+上市年+集采状态 | ◐ |
| 专利到期 | patent_expiry | date | 专利登记平台/人工 | ✗ |
| 仿制药家数 | followers_count | int | 派生：同分子 distinct 厂家数 | ◐ 依赖注册库 |
| 是否独家 | is_exclusive | bool | 派生：followers_count=1 | ◐ 派生 |

## 3. 医保层
| 展示项 | 字段名 | 类型 | 来源/计算 | 现状 |
| :--- | :--- | :--- | :--- | :--- |
| 医保状态 | insurance_status | enum | 国谈/常规医保/自费（由目录类别派生） | ◐ |
| 目录类别 | insurance_category | text | drug_insurance_entry.category（甲/乙） | ✅ |
| 国家医保编码 | insurance_code | text | drug_insurance_entry.insurance_code | ◐ |
| 目录版本 | insurance_catalog_version | text | insurance_catalog.version_name | ✅ 2 版 |
| 进入医保年份 | insurance_since_year | int | 首个目录版本年份 | ◐ |
| 报销比例/自付 | reimbursement_ratio | text | drug_insurance_entry（省版） | ✗ 空列已建 |
| 支付范围限制 | payment_scope | text | drug_insurance_entry.payment_scope | ◐ |
| 支付标准 | pay_standard | text | insurance_catalog_entry.pay_standard | ◐ |
| 双通道 | dual_channel | bool | 国家医保局双通道名单（新源） | ✗ |
| 地方增补 | supplement_status | text | drug_insurance_entry（省版） | ✗ 空列已建 |
| 国谈情况 | negotiation | json | 新表 negotiation_result（批次/协议期/价格） | ✗ |

## 4. 价格/集采/市场层
| 展示项 | 字段名 | 类型 | 来源/计算 | 现状 |
| :--- | :--- | :--- | :--- | :--- |
| 最新挂网价 | latest_listed_price | num | price_history(type=挂网, 最新) | schema✅ 数据✗ |
| 挂网价地区/日期 | listed_price_region/date | text/date | price_history | ✗ |
| 集采价 | vbp_price | num | procurement_result.price（官方公告） | ◐ 12批文件无价 |
| 集采批次/中选企业 | vbp_events[] | json[] | procurement_result 聚合 | ◐ 752 行 |
| 集采风险 | vbp_risk_level | enum | 派生：中选情况+过评家数+降幅 | ◐ |
| 红标/黄标 | price_flag | text | price_history（省×时间） | schema✅ 数据✗ |
| 年化费用 | annual_cost | num | 派生：日剂量×价格×365（需用法用量结构化） | ✗ |
| 内部采购价 | internal_price | num | 内部/谈判数据 | ✗ |
| 市场占有率 | market_share | num | drug_market（数值+年份+来源） | ✗ 0 条 |
| 患者池 | patient_pool | text | 流行病学来源（癌种/慢病） | ✗ 现为前端硬编码 |
| 目标人群 | target_population | text | 适应症筛选规则/人工 | ✗ |
| DRG风险 | drg_risk | enum | 病种付费政策映射 | ✗ |
| 配送公司 | distributors[] | json[] | 商业/内部数据 | ✗ 后置 |
| 在用医院 | hospitals[] | json[] | 商业/内部数据 | ✗ 后置 |

## 5. 病种/竞争层
| 展示项 | 字段名 | 类型 | 来源/计算 | 现状 |
| :--- | :--- | :--- | :--- | :--- |
| 治疗领域 | therapeutic_area | text | 新字段（molecule/人工） | ✗ |
| 病种 | disease | text | 新字段（molecule/人工） | ✗ |
| 同病种品种数 | peers_count | int | 派生：同 disease 分子数 | ✗ 依赖病种字段 |

## 6. 政策关联层
| 展示项 | 字段名 | 类型 | 来源/计算 | 现状 |
| :--- | :--- | :--- | :--- | :--- |
| 相关政策 | policies[] | json[] | policy_drug_relation + policies | ✗ 0 关联 |
| 卡片要素 | policy{title,summary,advice,deadline,url} | json | 政策结构化字段（一策一页） | ◐ 待补 |

## 7. 派生/输出层
| 展示项 | 字段名 | 类型 | 来源/计算 | 现状 |
| :--- | :--- | :--- | :--- | :--- |
| 准入总分 | access_score_total | int | 六维加权（指南35/医保25/给药15/集采10/冷链10/DRG5） | ◐ |
| 评分明细 | score_breakdown | json | 同上（六项分值） | ◐ |
| 推荐等级 | recommendation_level | enum | A/B/C/D 阈值 | ◐ |
| 医院青睐度 | favor_score | int | 指南/医保/生命周期/费用/集采加权 | ◐ |
| 一句话结论 | conclusion_one_liner | text | 派生 + note 人工点评 | ◐ |
| 人工点评 | note | text | 人工 | ✗ |
| 数据溯源 | provenance | json | 各字段 source_url/更新时间 | 设计新增 |
| 更新时间 | updated_at | datetime | 视图生成时间 | ✅ |

## 8. drug_profile 视图的取数规则（SQL 层面）
```
drug_profile =
  drug_product + drug_registration(UNIQUE 文号)
  + molecule(route/cold_chain/atc/generation/guideline_level/iteration_chain)
  + 最新 leaflet(按 updated_at)
  + indications 聚合(数组)
  + insurance 当前版本(region=国家，附省版数组)
  + price_history 各类型最新(附地区/批次)
  + procurement_result 聚合(JSON 数组)
  + policy_drug_relation 聚合(JSON 数组)
  + 派生列(函数/SQL 计算)
```

## 9. 示例（奥希替尼，节选 JSON）
```json
{
  "approval_number": "国药准字J20171015",
  "generic_name": "奥希替尼",
  "trade_name": "泰瑞沙",
  "manufacturer": "阿斯利康",
  "dosage_form": "片剂", "specification": "80mg",
  "approval_date": "2017-03", "registration_class": "",
  "indications": ["EGFR T790M突变NSCLC", "一线EGFR突变NSCLC", "辅助治疗"],
  "mechanism_summary": "EGFR T790M抑制剂",
  "route": "口服", "cold_chain": "常温",
  "guideline_level": "", "generation": "第3代EGFR-TKI",
  "insurance_status": "常规医保", "insurance_code": "",
  "pay_standard": "", "dual_channel": null,
  "latest_listed_price": null, "vbp_events": [],
  "annual_cost": null, "market_share": null,
  "patient_pool": "肺癌年新发约82.8万例（中国，待替换为正式来源）",
  "policies": [],
  "access_score_total": 74, "recommendation_level": "B",
  "provenance": {"indications": ["CDE 说明书"], "insurance": ["医保目录2025"]}
}
```

## 10. 落地优先级
- v1（现有数据即可拼）：身份层 + 说明书层 + 医保现有字段 + 集采事件 + 少量派生；
- v2（需新来源/人工）：病种/领域、指南等级、双通道、国谈、专利、价格、患者池、点评与大白话；
- v3（内部/商业数据）：内部采购价、配送公司、在用医院。
