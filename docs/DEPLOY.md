# 🚀 คู่มือขึ้นเซิร์ฟเวอร์จริง + โดเมน (Production Deploy)

เป้าหมาย: ให้ SentinelAI มีลิงก์จริง (เช่น `https://sentinelai.co.th`) ที่ลูกค้าสมัครและใช้ได้เลย รองรับคนจำนวนมาก

> **ค่าใช้จ่ายโดยประมาณ:** โดเมน ~300–500 บาท/ปี + เซิร์ฟเวอร์ ~150–350 บาท/เดือน = เริ่มได้ที่หลักร้อยบาท/เดือน
> **สิ่งที่เตรียมไว้ให้แล้ว:** `Dockerfile`, `docker-compose.yml`, `Caddyfile` (HTTPS อัตโนมัติ), `.env.production.example`

---

## ภาพรวม 5 ขั้น
```
1. จดโดเมน        →  2. เช่าเซิร์ฟเวอร์  →  3. ชี้ DNS  →  4. Deploy (Docker)  →  5. เสร็จ! HTTPS อัตโนมัติ
```

---

## ขั้น 1 — จดโดเมน (~5 นาที, จ่ายเงินครั้งเดียว/ปี)
1. ไป [Cloudflare](https://dash.cloudflare.com) (แนะนำ ถูก+ฟรี DNS) หรือ [Namecheap](https://namecheap.com) / [GoDaddy](https://godaddy.com)
2. ค้นหาชื่อโดเมนที่อยากได้ (เช่น `sentinelai.co.th`, `sentinel-ai.com`) → กดซื้อ
3. จ่ายเงิน (บัตรเครดิต/PayPal) → ได้โดเมนมา

## ขั้น 2 — เช่าเซิร์ฟเวอร์ (~5 นาที, จ่ายรายเดือน)

### 🥇 แนะนำ: BytePlus ECS (เพราะคุณมีบัญชีอยู่แล้ว!)
ข้อดี: **บิลเดียวกับ AI**, อยู่ **ภูมิภาคเดียวกับ ModelArk (ap-southeast)** → เรียก AI เร็ว, จัดการที่เดียว
1. [BytePlus Console](https://console.byteplus.com) → **ECS (Elastic Compute Service)** → Create Instance
2. Region: **Asia Pacific (Southeast)** — ให้ตรงกับ ModelArk
3. Image: **Ubuntu 24.04** · Instance: g-series **2 vCPU / 4 GB** (ขยายทีหลังได้)
4. เปิด **Security Group** ให้ port **80** และ **443** (และ 22 สำหรับ SSH)
5. จดเลข **Public IP** ที่ได้มา

### ทางเลือกอื่น
[Hetzner](https://hetzner.com) (~€4/เดือน) · [DigitalOcean](https://digitalocean.com) · [Vultr](https://vultr.com) — เลือก Ubuntu 24.04, 2vCPU/4GB, จด IP

## ขั้น 3 — ชี้โดเมนมาที่เซิร์ฟเวอร์ (DNS)
ที่หน้าจัดการโดเมน (Cloudflare/registrar) → เพิ่ม record:

| Type | Name | Value |
|---|---|---|
| A | `@` (หรือชื่อโดเมน) | `203.0.113.10` (IP เซิร์ฟเวอร์) |
| A | `www` | `203.0.113.10` |

> ถ้าใช้ Cloudflare: ตั้ง proxy เป็น **"DNS only" (เมฆสีเทา)** ตอนแรก เพื่อให้ Caddy ขอ HTTPS ได้

## ขั้น 4 — Deploy (บนเซิร์ฟเวอร์)
SSH เข้าเซิร์ฟเวอร์ (`ssh root@203.0.113.10`) แล้วทำตามนี้:

```bash
# 4.1 ติดตั้ง Docker (ครั้งเดียว)
curl -fsSL https://get.docker.com | sh

# 4.2 เอาโค้ดขึ้นเซิร์ฟเวอร์ (วิธีง่าย: git หรือ scp ทั้งโฟลเดอร์โปรเจกต์)
#     เช่น  git clone <repo ของคุณ>  แล้ว cd เข้าโฟลเดอร์
cd sentinelai   # โฟลเดอร์โปรเจกต์

# 4.3 ตั้งค่า .env (สำคัญ!)
cp backend/.env.production.example backend/.env
python3 -c "import secrets;print(secrets.token_urlsafe(48))"   # คัดลอกไปใส่ SENTINEL_JWT_SECRET
nano backend/.env    # ใส่ SENTINEL_JWT_SECRET, SENTINEL_ADMIN_EMAILS (อีเมลคุณ), ARK_API_KEY

# 4.4 ใส่โดเมนใน Caddyfile
nano Caddyfile       # เปลี่ยน your-domain.com เป็นโดเมนจริง

# 4.5 รัน!
docker compose up -d --build
```

## ขั้น 5 — เสร็จ! ✅
เปิดเบราว์เซอร์ไปที่ **`https://โดเมนของคุณ`** → เจอหน้าสมัคร/ล็อกอิน SentinelAI
- Caddy ขอใบรับรอง **HTTPS ให้อัตโนมัติ** (รอ ~1 นาทีครั้งแรก)
- **บัญชีแรกที่คุณสมัคร** (อีเมลตรงกับ `SENTINEL_ADMIN_EMAILS`) = **Super Admin** เจ้าของแพลตฟอร์ม

---

## 🧾 ขายจริง: รับลูกค้ายังไง
1. ลูกค้าเข้าเว็บ → **สมัคร** (ได้ทดลองฟรี 14 วันอัตโนมัติ)
2. ลูกค้าติดตั้ง Extension/Agent ด้วย API key ของเขา (หน้า "ติดตั้ง & ตั้งค่า")
3. ลูกค้าจ่ายเงิน → คุณเข้า **👑 Super Admin** → เปลี่ยนสถานะเป็น **Active** + ตั้ง seat/quota ตามแพ็กเกจ
4. ถ้าไม่จ่าย/หมดอายุ → ระบบ **บล็อกอัตโนมัติ** (license enforcement)

## 📈 พอคนเยอะขึ้น (Scale) — ใช้บริการ BytePlus ต่อยอดได้
ระบบตอนนี้ใช้ **SQLite** — พอสำหรับช่วงเริ่มต้น (ลูกค้าหลักสิบ–ร้อย, เหตุการณ์หลักแสน)
เมื่อโตขึ้น ต่อยอดด้วยบริการอื่นของ BytePlus ได้เลย (อยู่ระบบเดียวกัน):

| ต้องการ | บริการ BytePlus |
|---|---|
| ฐานข้อมูลรองรับคนเยอะ | **RDS / Managed PostgreSQL** (แทน SQLite) |
| กระจายโหลดหลายเครื่อง | **CLB (Cloud Load Balancer)** + ECS หลายตัว |
| เก็บ/แจกไฟล์ดาวน์โหลด (extension/agent) | **TOS (Object Storage)** |
| เว็บเร็วทั่วโลก | **CDN** |
| สมอง AI | **ModelArk** (ใช้อยู่แล้ว) |

ขั้นตอนย้ายไป Postgres: เพิ่ม `--workers 4` ใน Dockerfile + เปลี่ยน `app/db.py` (บอกผม เดี๋ยวทำ migration ให้)

## 🔀 ทางเลือกที่ง่ายกว่า VPS (ไม่ต้องดูแลเซิร์ฟเวอร์เอง)
- **Railway / Render**: เชื่อม GitHub repo → มันจะ build จาก Dockerfile ให้ + แจก HTTPS + ใส่ custom domain ได้
- เหมาะถ้าไม่อยากยุ่งกับ SSH/Docker เอง (แต่ค่าบริการอาจสูงกว่า VPS เล็กน้อย)

## 💳 เก็บเงินอัตโนมัติ (ขั้นถัดไป)
ตอนนี้เก็บเงินแบบ manual (ลูกค้าโอน → คุณกด Active ใน Super Admin) ซึ่งพอสำหรับช่วงแรก
ถ้าต้องการรับเงินอัตโนมัติ (บัตร/พร้อมเพย์) เชื่อม **Stripe** หรือ **Omise** ได้ — บอกผมเมื่อพร้อม

---

## ✅ เช็กลิสต์ก่อน Go Live
- [ ] ตั้ง `SENTINEL_JWT_SECRET` เป็นค่าสุ่ม (ห้ามใช้ค่าตัวอย่าง)
- [ ] ตั้ง `SENTINEL_ADMIN_EMAILS` = อีเมลคุณ (เพื่อเป็น Super Admin)
- [ ] ใส่ `ARK_API_KEY` (เปิดใช้สมอง AI)
- [ ] เปลี่ยนโดเมนใน `Caddyfile`
- [ ] Activate โมเดลใน BytePlus Console
- [ ] ทดสอบ: สมัคร → ติดตั้ง extension → ลองวางข้อมูลลับ → เห็นใน dashboard
