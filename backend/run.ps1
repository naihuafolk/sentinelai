# SentinelAI — สคริปต์รัน backend (Windows PowerShell)
# ใช้:  คลิกขวา > Run with PowerShell  หรือ  .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "🛡️  SentinelAI — กำลังเตรียมระบบ..." -ForegroundColor Green

# ติดตั้ง dependency ถ้ายังไม่ครบ
python -c "import fastapi, uvicorn, httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ติดตั้ง dependencies..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "สร้าง .env จากตัวอย่างแล้ว (ใส่ ARK_API_KEY เพื่อเปิดใช้ AI)" -ForegroundColor Yellow
}

Write-Host "เปิด Dashboard ที่ http://127.0.0.1:8000" -ForegroundColor Cyan
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
