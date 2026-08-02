#!/bin/bash
# SentinelAI Endpoint Agent — ตัวติดตั้งสำหรับ macOS
# ดับเบิลคลิกไฟล์นี้เพื่อติดตั้ง (เฝ้าคลิปบอร์ดทั้งเครื่อง + เปิดอัตโนมัติตอนล็อกอิน)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
echo "============================================================"
echo " 🛡️  SentinelAI Agent — ติดตั้งบน macOS"
echo "============================================================"

# 1) ตรวจ Python 3
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ ไม่พบ Python 3"
  echo "   โปรดติดตั้งจาก https://www.python.org/downloads/ (เลือกตัว macOS) แล้วรันไฟล์นี้อีกครั้ง"
  read -p "กด Enter เพื่อปิด..."; exit 1
fi
PY="$(command -v python3)"
echo "• พบ Python: $PY"

# 2) ติดตั้งไลบรารีที่จำเป็น
echo "• กำลังติดตั้งไลบรารี (httpx, pillow)..."
"$PY" -m pip install --user --quiet httpx pillow 2>/dev/null || "$PY" -m pip install --quiet httpx pillow

# 3) ตั้งค่า Org Key (ถ้ายังไม่มี)
if [ ! -f "$DIR/sentinel.env" ]; then
  echo ""
  echo "🔑 วาง Org Key ขององค์กร (คัดลอกจากเว็บ SentinelAI → แท็บ ตั้งค่า):"
  read -r KEY
  {
    echo "SENTINEL_ORG_KEY=$KEY"
    echo "SENTINEL_BACKEND_URL=https://sentinelai.help"
  } > "$DIR/sentinel.env"
  echo "• บันทึกการตั้งค่าแล้ว"
fi

# 4) สร้าง LaunchAgent เปิดอัตโนมัติตอนล็อกอิน
PLIST="$HOME/Library/LaunchAgents/com.sentinelai.agent.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.sentinelai.agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$DIR/clipboard_guard.py</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo ""
echo "============================================================"
echo " ✅ ติดตั้งเสร็จ! SentinelAI Agent กำลังเฝ้าคลิปบอร์ด"
echo "    และจะเปิดเองอัตโนมัติทุกครั้งที่ล็อกอิน"
echo "    (ถ้า macOS ถามสิทธิ์เข้าถึงหน้าจอ/คลิปบอร์ด โปรดกด 'อนุญาต')"
echo "============================================================"
read -p "กด Enter เพื่อปิด..."
