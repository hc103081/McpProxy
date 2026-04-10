# McpProxy 管理員啟動腳本 (PowerShell)
# 此腳本會檢查權限，若不足則觸發 UAC 提升並在新視窗中執行，且保持視窗開啟直到結束。

$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "--------------------------------------------------" -ForegroundColor Cyan
    Write-Host " [!] 偵測到權限不足，正在請求系統管理員權限..." -ForegroundColor Yellow
    Write-Host "--------------------------------------------------" -ForegroundColor Cyan
    
    # 使用 Start-Process 觸發 UAC，並傳遞目前腳本路徑
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host " [+] 已進入管理員模式，啟動 McpProxy..." -ForegroundColor Green
Write-Host "--------------------------------------------------" -ForegroundColor Cyan

# 執行主程式
python main.py

Write-Host "`n程序已結束，按下任意鍵關閉視窗..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
