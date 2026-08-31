# 药品数据每日自动更新：NMPA 增量采集 → 医保目录重跑 → 快照导出 → 自动推送
# 注册为 Windows 计划任务（见文件末尾命令）
$ErrorActionPreference = "Continue"
$repo = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path (Join-Path $repo "repo"))) { $repo = $PSScriptRoot }
$crawler = Join-Path $repo "outputs\policy-crawler"
if (-not (Test-Path $crawler)) { $crawler = Join-Path $repo "policy-crawler" }
$log = Join-Path $repo "logs\daily-update.log"
New-Item -ItemType Directory -Path (Split-Path $log -Parent) -Force | Out-Null

function Write-Log($msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  ("$ts $msg") | Out-File -FilePath $log -Append -Encoding utf8
  Write-Host "$ts $msg"
}

Write-Log "=== 每日更新开始 ==="
Set-Location $crawler

# 1) NMPA 官方注册数据增量采集（含详情；失败自动重试）
Write-Log "步骤1/4 NMPA 增量采集..."
python -u tools\backfill_nmpa.py --db policy_crawler.db --max-pages 20 --details 50 --retries 2 --delay 3 2>&1 | ForEach-Object { Write-Log $_ }

# 2) 医保目录重跑（自动发现最新版目录 PDF）
Write-Log "步骤2/4 医保目录更新..."
python -u -m importers.insurance_catalog --auto --db policy_crawler.db 2>&1 | ForEach-Object { Write-Log $_ }

# 3) 生成站点快照 data/drugs.json
Write-Log "步骤3/4 生成快照..."
python -u tools\export_drugs_snapshot.py --db policy_crawler.db --out (Join-Path $repo "repo\data\drugs.json") 2>&1 | ForEach-Object { Write-Log $_ }

# 4) 提交并推送
Write-Log "步骤4/4 提交推送..."
Set-Location (Join-Path $repo "repo")
git add data/drugs.json data/policies.json 2>&1 | ForEach-Object { Write-Log $_ }
if (git diff --cached --quiet) {
  Write-Log "无数据变更，跳过提交"
} else {
  git commit -m "chore: auto-update drug/policy data [skip ci]" 2>&1 | ForEach-Object { Write-Log $_ }
  git push 2>&1 | ForEach-Object { Write-Log $_ }
}

Write-Log "=== 每日更新完成 ==="

# 注册计划任务（管理员 PowerShell 执行一次）：
# schtasks /Create /TN "DrugToolDailyUpdate" /TR "powershell -ExecutionPolicy Bypass -File `"C:\Users\YUWZZ\Documents\Codex\2026-08-07\github-plugin-github-openai-api-curated\outputs\run_daily_update.ps1`"" /SC DAILY /ST 08:30 /F
