# Wave-1 执行清单（价格 / 双通道 / 国谈 / 病种分类）

更新时间：2026-09-16

## 一、本轮已完成（代码 + 已入库数据）

| 项目 | 状态 | 关键数字 |
| :--- | :--- | :--- |
| 病种/治疗领域分类 | ✅ 已入库 | 85 个分子中 83 个已分类（高 51 / 中 18 / 低 14） |
| 国谈（谈判/竞价） | ✅ 已入库 | negotiation_result 944 条，其中 42 条回挂分子 |
| 双通道（湖南） | ✅ 已入库 | dual_channel 584 条（湖南 2026Q2 官方名单） |
| 双通道（上海） | ⏳ 代码就绪待写入 | 上海首批名单 96 条（解析验证通过） |
| 挂网价（湖南） | ✅ 已入库 | price_history 湖南 309 条（最小制剂价格口径） |
| 医保支付标准（上海） | ⏳ 代码就绪待写入 | 2025 目录谈判部分：472 条目、152 条含金额 |
| 销售数据（公开） | ⏸ 未开始 | 需先确定公开来源口径 |

数据来源（均为官方公开文件）：

- 湖南：`2026年二季度湖南省药品价格信息公布表`（含挂网价 / 是否双通道 / 是否国谈 / 是否集采中选）
  http://ybj.hunan.gov.cn/ybj/first113541/firstF/info1/202608/t20260806_34040891.html
- 上海（双通道名单）：沪医保医管发〔2021〕40 号 附件「上海市纳入"双通道"管理的药品名单」
  http://ybj.sh.gov.cn/qtwj/20211130/b4e8016fe52145e384b81159cce7fd13.html
- 上海（支付标准）：《国家医保目录（2025年）》上海执行版（协议期内谈判药品部分）
  http://ybj.sh.gov.cn/qtwj/20260104/3d5b634c0163425aad9dabd9d3efae52.html

## 二、待你本地执行的三条命令（补完写入）

> 背景：本机自动审批今天拦截了"脚本批量写库"类命令，只读/干跑正常；
> 你本地终端可以直接跑。

```powershell
cd C:\Users\YUWZZ\Documents\Codex\2026-08-07\github-plugin-github-openai-api-curated\outputs\policy-crawler

# 1) 上海双通道名单（96 条）
python tools\import_shanghai_dual_channel.py --db policy_crawler.db --pdf logs\regional\4071d1129606b6775649edf23b48f433.pdf

# 2) 上海医保支付标准（谈判药品部分）
python tools\import_shanghai_payment_standard.py --db policy_crawler.db --pdf logs\regional\aaf2ae7d166f3c2bc6da66ee98a55f23.pdf

# 3) 湖南价格/双通道（用新的"最长词干"匹配口径重跑一遍，回挂率更高）
python tools\import_regional_hunan.py --db policy_crawler.db --xlsx logs\regional\hunan_2026q2_price.xlsx

# 4) 重新导出站点快照
python tools\export_drugs_snapshot.py --db policy_crawler.db --out ..\..\repo\data\drugs.json
```

## 三、已知阻塞与风险

1. **上海阳光医药采购网（smpaa.cn）**：返回 403（含真实浏览器），IP/区域级拦截，
   暂以医保局公开文件替代；如后续需要挂网价明细，建议你在上海本地网络访问后另存文件再导入。
2. **品种覆盖率是主要瓶颈**：湖南价格表 12.4 万行中仅 316 个品种能回挂
   （本库 901 个批准文号 vs 全省在挂品种规模），上海谈判药品 152 条含金额条目中也只有 3 条能回挂。
   → 下一步优先做"品种充盈"（NMPA 反查补齐批准文号）。
3. **销售数据**：公开渠道暂无稳定结构化来源，暂不填入（遵循"无源不填"）。
4. 每日 NMPA 增量任务仍在后台运行（写入同一库）；跑完后建议再执行一次第 4 步导出快照。

## 四、验证方式

```powershell
# 单元测试（当前 165 项）
python -m unittest discover -s tests -p "test*.py" -t .

# 前端展示校验（本地起服务 + 浏览器断言）
python tools\qa_wave1_frontend.py 吡咯替尼
```
