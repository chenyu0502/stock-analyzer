#Requires -Version 5.1
<#
.SYNOPSIS
    一鍵建立「持股分析」Windows 排程任務（需以管理員身份執行）
.DESCRIPTION
    建立兩個排程任務：
    - AntigravityPortfolio_Morning   → 每個交易日 09:00
    - AntigravityPortfolio_Afternoon → 每個交易日 14:30
    兩者均執行 analyze_portfolio.py，並將 stdout/stderr 記錄到 logs\ 目錄。
.NOTES
    執行方式（以管理員開啟 PowerShell）：
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    cd d:\ZZ_Chenyu\Antigravity
    .\setup_task_scheduler.ps1
#>

# ── 設定區 ────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$PythonScript = Join-Path $ScriptDir "analyze_portfolio.py"
$LogDir = Join-Path $ScriptDir "logs"
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $PythonExe) {
    Write-Host "[ERROR] 找不到 python 執行檔，請確認 Python 已加入 PATH。" -ForegroundColor Red
    exit 1
}

# 建立 logs 目錄
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# ── 安裝 yfinance（如尚未安裝）──────────────────────────────────
Write-Host "`n[SETUP] 檢查 yfinance..." -ForegroundColor Cyan
$installed = & $PythonExe -c "import yfinance; print('ok')" 2>$null
if ($installed -ne 'ok') {
    Write-Host "        安裝 yfinance..." -ForegroundColor Yellow
    & $PythonExe -m pip install yfinance --quiet
    Write-Host "        ✓ yfinance 已安裝" -ForegroundColor Green
}
else {
    Write-Host "        ✓ yfinance 已存在" -ForegroundColor Green
}

# ── 建立排程任務函式 ──────────────────────────────────────────
function New-PortfolioTask {
    param(
        [string]$TaskName,
        [int]   $Hour,
        [int]   $Minute
    )

    $LogFile = Join-Path $LogDir "task_$($Hour.ToString('D2'))$($Minute.ToString('D2')).log"

    # Action：python analyze_portfolio.py >> log 2>&1
    $CmdArgs = "/c `"cd /d `"$ScriptDir`" && `"$PythonExe`" `"$PythonScript`" >> `"$LogFile`" 2>&1`""
    $Action = New-ScheduledTaskAction `
        -Execute "cmd.exe" `
        -Argument $CmdArgs `
        -WorkingDirectory $ScriptDir

    # Trigger：每週一至五，指定時間
    $Trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
        -At "${Hour}:${Minute}"

    # Settings
    $Settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
        -RestartCount 1 `
        -RestartInterval (New-TimeSpan -Minutes 2) `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable

    # Principal（目前登入使用者）
    $Principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType S4U `
        -RunLevel Highest

    # 若任務已存在則先刪除
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask `
        -TaskName  $TaskName `
        -Action    $Action `
        -Trigger   $Trigger `
        -Settings  $Settings `
        -Principal $Principal `
        -Description "Antigravity 持股分析 ($($Hour):$($Minute.ToString('D2')))" `
    | Out-Null

    Write-Host "  ✓ [$TaskName] 已建立 → 執行時間：每交易日 $($Hour):$($Minute.ToString('D2'))" -ForegroundColor Green
    Write-Host "     日誌位置：$LogFile"
}

# ── 建立兩個任務 ──────────────────────────────────────────────
Write-Host "`n[SCHEDULER] 建立排程任務..." -ForegroundColor Cyan
New-PortfolioTask -TaskName "AntigravityPortfolio_Morning"   -Hour 9  -Minute 0
New-PortfolioTask -TaskName "AntigravityPortfolio_Afternoon" -Hour 14 -Minute 30

# ── 驗證 ─────────────────────────────────────────────────────
Write-Host "`n[VERIFY] 確認任務狀態..." -ForegroundColor Cyan
@("AntigravityPortfolio_Morning", "AntigravityPortfolio_Afternoon") | ForEach-Object {
    $task = Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue
    if ($task) {
        $nextRun = ($task | Get-ScheduledTaskInfo).NextRunTime
        Write-Host "  ✓ $_ → 狀態：$($task.State)  下次執行：$nextRun" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $_ 建立失敗！" -ForegroundColor Red
    }
}

# ── 提示立即測試 ──────────────────────────────────────────────
Write-Host @"

──────────────────────────────────────────
  排程設定完成！

  立即測試（可選）：
    cd "$ScriptDir"
    python analyze_portfolio.py

  開啟儀表板：
    Start-Process "$ScriptDir\dashboard\index.html"

  查看排程任務 GUI：
    taskschd.msc
──────────────────────────────────────────
"@ -ForegroundColor Cyan
