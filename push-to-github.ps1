# 一键推送到 GitHub（需在你自己电脑的终端运行，沙箱内无外网）
# 用法：powershell -ExecutionPolicy Bypass -File .\push-to-github.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Codex 自带精简 git 默认找不到 git-remote-https，自动定位并启用
$gitExe = (Get-Command git -ErrorAction SilentlyContinue).Source
if ($gitExe -and $gitExe -match "codex-runtimes") {
  $gitRoot = Split-Path (Split-Path $gitExe -Parent) -Parent
  $helperBin = Join-Path $gitRoot "mingw64\bin"
  if (Test-Path (Join-Path $helperBin "git-remote-https.exe")) {
    $env:GIT_EXEC_PATH = $helperBin
    $env:PATH = "$helperBin;$env:PATH"
    Write-Host "==> 已启用 git-remote-https 助手: $helperBin"
  }
}

$remote = "https://github.com/yuwzz0210/drug-tool.git"

if (-not (git remote | Select-String -Quiet "origin")) {
  git remote add origin $remote
}
git remote set-url origin $remote

Write-Host "==> 拉取远端（保留线上历史）..."
git fetch origin 2>&1 | Out-Null

$hasMain = git branch -r | Select-String -Quiet "origin/main"
if ($hasMain) {
  Write-Host "==> 合并线上历史（冲突时以本地最新文件为准）..."
  git merge origin/main --allow-unrelated-histories -X ours --no-edit
}

Write-Host "==> 推送 main ..."
git push -u origin main
Write-Host "==> 完成。GitHub Actions 每日 08:00/20:00（北京时间）自动抓取并更新 data/policies.json"
