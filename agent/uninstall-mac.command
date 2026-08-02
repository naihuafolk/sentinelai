#!/bin/bash
# SentinelAI Endpoint Agent — ถอนการติดตั้งบน macOS
PLIST="$HOME/Library/LaunchAgents/com.sentinelai.agent.plist"
echo "🛡️  SentinelAI Agent — กำลังถอนการติดตั้ง..."
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "✅ ถอนการติดตั้งแล้ว (Agent จะไม่เปิดอัตโนมัติอีก)"
echo "   หมายเหตุ: ไฟล์โฟลเดอร์นี้ยังอยู่ — ลบทิ้งเองได้ถ้าต้องการ"
read -p "กด Enter เพื่อปิด..."
