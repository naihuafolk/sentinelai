#!/usr/bin/env bash
# ============================================================================
# SentinelAI — สคริปต์ deploy คำสั่งเดียวจบ (รันบนเซิร์ฟเวอร์ Ubuntu)
# ใช้:  sudo bash deploy.sh
# ============================================================================
set -e
cd "$(dirname "$0")"

echo "🛡️  SentinelAI — ติดตั้งขึ้น Production"
echo "============================================"

# 1) ติดตั้ง Docker ถ้ายังไม่มี
if ! command -v docker >/dev/null 2>&1; then
  echo "→ ติดตั้ง Docker..."
  curl -fsSL https://get.docker.com | sh
fi

# 2) รับค่าที่จำเป็น
read -rp "โดเมนของคุณ (เช่น sentinelai.co.th): " DOMAIN
read -rp "อีเมล Super Admin (เจ้าของแพลตฟอร์ม): " ADMIN_EMAIL
read -rp "ARK_API_KEY (BytePlus): " ARK_KEY

if [ -z "$DOMAIN" ] || [ -z "$ADMIN_EMAIL" ] || [ -z "$ARK_KEY" ]; then
  echo "❌ ต้องกรอกให้ครบทั้ง 3 ค่า"; exit 1
fi

# 3) สร้าง JWT secret แบบสุ่ม
JWT=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))" 2>/dev/null || openssl rand -base64 48 | tr -d '\n')

# 4) เขียนไฟล์ backend/.env
cat > backend/.env <<EOF
ARK_API_KEY=${ARK_KEY}
ARK_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3
ARK_MODEL_REASONING=dola-seed-2-1-turbo-260628
ARK_MODEL_FAST=dola-seed-2-1-turbo-260628
ARK_MODEL_VISION=dola-seed-2-1-turbo-260628
ARK_MODEL_EMBEDDING=skylark-embedding-vision-251215
SENTINEL_JWT_SECRET=${JWT}
SENTINEL_ADMIN_EMAILS=${ADMIN_EMAIL}
SENTINEL_ENFORCE_LICENSE=true
SENTINEL_TRIAL_DAYS=14
SENTINEL_DEFAULT_MODE=warn
SENTINEL_AI_RISK_THRESHOLD=35
SENTINEL_STORE_CONTENT=false
SENTINEL_DB_PATH=/data/sentinel.db
SENTINEL_CORS_ORIGINS=*
EOF
echo "→ สร้าง backend/.env แล้ว (JWT secret สุ่มให้อัตโนมัติ)"

# 5) ใส่โดเมนใน Caddyfile
sed -i "s/your-domain.com/${DOMAIN}/g" Caddyfile
echo "→ ตั้งโดเมน ${DOMAIN} ใน Caddyfile แล้ว"

# 6) รัน!
echo "→ กำลัง build + start (ครั้งแรกอาจใช้เวลา 2-3 นาที)..."
docker compose up -d --build

echo ""
echo "============================================"
echo "✅ เสร็จ! เปิด:  https://${DOMAIN}"
echo "   (รอ ~1 นาที ให้ Caddy ขอใบรับรอง HTTPS)"
echo "   บัญชีแรกที่สมัครด้วยอีเมล ${ADMIN_EMAIL} = Super Admin"
echo ""
echo "ตรวจสถานะ:  docker compose ps"
echo "ดู log:      docker compose logs -f app"
echo "============================================"
