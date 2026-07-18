#!/usr/bin/env bash
# SentinelAI — สคริปต์รัน backend (macOS / Linux / Git Bash)
set -e
cd "$(dirname "$0")"

echo "🛡️  SentinelAI — กำลังเตรียมระบบ..."
if ! python -c "import fastapi, uvicorn, httpx" 2>/dev/null; then
  echo "ติดตั้ง dependencies..."
  python -m pip install -r requirements.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "สร้าง .env จากตัวอย่างแล้ว (ใส่ ARK_API_KEY เพื่อเปิดใช้ AI)"
fi

echo "เปิด Dashboard ที่ http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
