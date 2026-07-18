# 🛡️ SentinelAI — AI Data Loss Prevention (AI-DLP)

> แพลตฟอร์มป้องกัน **ข้อมูลลับองค์กรรั่วไหลสู่เครื่องมือ AI สาธารณะ** (ChatGPT, Gemini, Claude, Copilot, DeepSeek ฯลฯ)
> ขับเคลื่อนการเข้าใจเชิงความหมายด้วย **BytePlus ModelArk** — ระบบใช้งานได้จริง 100%

สร้างจากเอกสารคอนเซ็ปต์ `SentinelAI-แพลตฟอร์มป้องกันข้อมูลรั่วสู่AI.pdf` และทำให้เป็นระบบที่ **รันได้จริง**:
Backend (FastAPI) + Browser Extension (Chrome/Edge MV3) + Admin Dashboard

---

## ✨ ทำงานได้ทันที แม้ยังไม่มีคีย์ AI

ระบบออกแบบตามหลัก **Privacy-by-Design** และ **Defense-in-Depth**:

| ชั้น | เทคนิค | ต้องใช้ AI? |
|---|---|---|
| 1️⃣ Pattern/Regex | บัตร ปชช. (checksum), บัตรเครดิต (Luhn), API Key, บัญชี, อีเมล ฯลฯ | ❌ ในเครื่อง |
| 2️⃣ Fingerprinting | จับเอกสารลับที่ถูกคัดลอก **แม้เพียงบางส่วน** (char n-gram) | ❌ ในเครื่อง |
| 3️⃣ AI Semantic | เข้าใจ **ความหมาย/บริบท/ภาพ** หลายภาษา (กลยุทธ์, ดีลลับ, สลิป, บัตร) | ✅ BytePlus |

> **ชั้น 1–2 ทำงานได้ 100% โดยไม่ต้องมีคีย์หรืออินเทอร์เน็ต** เมื่อใส่ `ARK_API_KEY` ระบบจะเปิดชั้น AI ให้อัตโนมัติ (เรียกเฉพาะเคสเสี่ยงเพื่อคุมต้นทุน)

### 🧠 ความสามารถ AI (BytePlus ModelArk) — เปิดเมื่อใส่คีย์ + Activate โมเดล

| ฟีเจอร์ | ทำอะไร | ที่อยู่ |
|---|---|---|
| **Semantic Detection** | จับกลยุทธ์/ดีล M&A/IP/ความลับการค้าที่ไม่มี pattern (หลายภาษา) | `classifier/semantic.py` |
| **Vision DLP** | สแกนภาพถ่ายหน้าจอ/สลิป/บัตร ปชช./สัญญา ที่แนบเข้า AI (OCR) | `classifier/semantic.py` (`images`) |
| **Safe Rewrite** 🔥 | เขียนคำถามใหม่ให้ตัดข้อมูลลับออกแต่คงเจตนา — พนักงานยังได้คำตอบ | `rewrite.py` |
| **AI Response Scan** | สแกน "คำตอบจาก AI" (ขาเข้า): data leak / unsafe / injection / hallucination | `response_scan.py` → `POST /inspect-response` |
| **Prompt-Injection Guard** | จับความพยายามหลอก/ควบคุม AI (heuristic + AI) | `response_scan.py` |

---

## 🚀 เริ่มใช้งานใน 3 ขั้นตอน

### 1) รัน Backend + Dashboard

```bash
cd backend
python -m pip install -r requirements.txt      # ครั้งแรกครั้งเดียว
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

เปิดเบราว์เซอร์ที่ **http://127.0.0.1:8000** → Admin Dashboard
กด **"โหลดข้อมูลตัวอย่าง"** (หรือเรียก `POST /api/v1/admin/seed-demo`) เพื่อดูข้อมูลตัวอย่าง 14 วัน

> Windows PowerShell: ใช้ `python -m uvicorn ...` เหมือนกัน หรือดับเบิลคลิก `backend\run.ps1`

### 2) ติดตั้ง Browser Extension (Chrome / Edge)

1. เปิด `chrome://extensions` → เปิด **Developer mode**
2. **Load unpacked** → เลือกโฟลเดอร์ `extension/`
3. คลิกไอคอน 🛡️ → **ตั้งค่า** → กรอกอีเมล/แผนก/ชื่อเครื่อง (Backend URL = `http://127.0.0.1:8000`)

### 3) ทดสอบจริง

เปิด **chatgpt.com** แล้วลอง **วาง (Ctrl+V)** หรือพิมพ์แล้วกด Enter ด้วยข้อความเหล่านี้:

| ทดสอบ | ผลที่คาดหวัง |
|---|---|
| `API key: sk-proj-abcd1234efgh5678ijkl9012mnop3456` | ⛔ **บล็อก** (Restricted) |
| `เลขบัตรประชาชนลูกค้า 1101700207366` | 🛡️ **ปิดบังอัตโนมัติ** (PII) |
| `งบการเงินภายในยังไม่ประกาศ กำไรสุทธิ 214 ล้าน` | ⚠️ **เตือน/บล็อก** (Confidential) |
| `ขอสูตรต้มยำกุ้งหน่อย` | ✅ **ผ่าน** (ไม่รบกวน) |

ทุกเหตุการณ์จะปรากฏใน Dashboard แบบเรียลไทม์

---

## 🔑 เปิดใช้สมอง AI (BytePlus ModelArk)

1. คัดลอกไฟล์ตั้งค่า: `cd backend && copy .env.example .env` (mac/linux: `cp`)
2. ขอ API Key จาก [BytePlus ModelArk Console](https://console.byteplus.com) → ใส่ใน `.env`:

```ini
ARK_API_KEY=your-key-here
ARK_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3
ARK_MODEL_REASONING=seed-2-0-pro-260328              # สมอง Policy Engine (ล่าสุด)
ARK_MODEL_VISION=seed-2-0-pro-260328                 # อ่านภาพ/เอกสาร (multimodal)
ARK_MODEL_EMBEDDING=skylark-embedding-vision-251215  # ฝัง/ค้นความคล้าย
```

3. รีสตาร์ต backend → หน้า **ระบบ & โมเดล** ใน Dashboard จะขึ้น *"เชื่อมต่อ BytePlus ModelArk แล้ว"*
   ทดสอบการเชื่อมต่อได้ที่ `GET /api/v1/health?check_ai=true`

> **หมายเหตุ:** Model ID เปลี่ยนตามภูมิภาค/บัญชีของคุณได้ — ปรับใน `.env` ให้ตรงกับ Endpoint ที่คุณเปิดใน ModelArk
> BytePlus ModelArk เป็น **OpenAI-compatible** ระบบจึงเรียกผ่านมาตรฐานเดียวกับ OpenAI SDK

---

## 🧩 สถาปัตยกรรม

```
                    ┌────────────────────────────────────────────┐
  พนักงานวาง/พิมพ์   │  Browser Extension (MV3)                    │
  ลง chatgpt.com ──▶│  • ดัก paste / Enter / ปุ่มส่ง               │
                    │  • overlay เตือน (Shadow DOM)               │
                    └───────────────┬────────────────────────────┘
                                    │ POST /api/v1/inspect
                                    ▼
        ┌──────────────────────────────────────────────────────────┐
        │  Backend (FastAPI)                                        │
        │  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐  │
        │  │ Classifier  │──▶│ Policy Engine │──▶│ Redact / Block │  │
        │  │ 3 ชั้น       │   │ (M3)          │   │ (M4)           │  │
        │  └──────┬──────┘   └──────────────┘   └────────┬───────┘  │
        │         │ ชั้น 3: AI                            │          │
        │         ▼                                       ▼          │
        │   BytePlus ModelArk                       Audit Log (M6)   │
        │   (reasoning/vision/embed)                sqlite, PDPA-min  │
        └──────────────────────────┬───────────────────────────────┘
                                   │ /stats /events /policies
                                   ▼
                        Admin Dashboard (M5) — เสิร์ฟที่ /
```

**7 โมดูลตามเอกสาร** → mapping ในโค้ด:

| โมดูล | ที่อยู่ในระบบ |
|---|---|
| M1 Data Discovery & Classification | `app/classifier/` + `POST /fingerprints` + `agent/file_scanner.py` (สแกนไฟล์ในเครื่อง) |
| M2 AI Channel Monitor | `extension/content/interceptor.js` (เบราว์เซอร์) + `agent/clipboard_guard.py` (นอกเบราว์เซอร์) |
| M3 Policy Engine | `app/policy/` |
| M4 Real-time Alert & Redaction | `extension/content/overlay.js` + `app/redaction.py` |
| M5 Admin Dashboard & Analytics | `dashboard/` + `app/audit.py` |
| M6 Audit Log & Compliance | `app/db.py` + `GET /events.csv` |
| M7 Employee Coaching | ข้อความ coaching ใน policy + overlay |

---

## 📚 เอกสารเพิ่มเติม

- [`docs/API.md`](docs/API.md) — API reference ครบทุก endpoint
- [`docs/DEMO.md`](docs/DEMO.md) — สคริปต์สาธิตทีละขั้น
- [`docs/BYTEPLUS.md`](docs/BYTEPLUS.md) — การตั้งค่าโมเดล BytePlus แต่ละจุด
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — 🚀 ขึ้นเซิร์ฟเวอร์จริง + โดเมน (Docker + HTTPS อัตโนมัติ)

## 🗂️ โครงสร้างโปรเจกต์

```
ระบบรักษาความปลอดภัย/
├─ backend/            # FastAPI — เครื่องยนต์ทั้งหมด
│  ├─ app/
│  │  ├─ classifier/   # 3 ชั้น: patterns / fingerprint / semantic (AI)
│  │  ├─ policy/       # Policy Engine + นโยบายเริ่มต้น
│  │  ├─ byteplus/     # ตัวเชื่อม BytePlus ModelArk (OpenAI-compatible)
│  │  ├─ main.py       # API + เสิร์ฟ dashboard
│  │  ├─ service.py    # Interception Flow
│  │  ├─ db.py audit.py redaction.py seed.py config.py schemas.py
│  ├─ tests/test_core.py
│  └─ requirements.txt .env.example
├─ extension/          # Chrome/Edge MV3 (ดักจับในเบราว์เซอร์)
│  ├─ content/ (sites, overlay, interceptor)  background.js  popup.*  options.*
├─ agent/              # Endpoint Agent (นอกเบราว์เซอร์)
│  ├─ clipboard_guard.py   # เฝ้าคลิปบอร์ดระดับ OS (ทุกแอป)
│  ├─ file_scanner.py      # สแกนไฟล์ลับในเครื่อง (Data Discovery)
│  └─ common.py  README.md
├─ dashboard/          # Admin Console (เสิร์ฟที่ /)
├─ SentinelAI-Web.html # เว็บเดโมแบบเปิดได้ทันที (ดับเบิลคลิก ไม่ต้องรันเซิร์ฟเวอร์)
└─ docs/
```

## 🧪 ทดสอบ

```bash
cd backend && python tests/test_core.py      # 23 เคส: validators / 3 ชั้น / AI merge / redaction / policy
```

## ✅ สถานะตาม Roadmap ในเอกสาร

- ✅ **เฟส 1 (MVP):** Extension + Regex/Pattern classifier + ดัก paste/submit + Dashboard
- ✅ **เฟส 2 (AI Brain):** BytePlus reasoning + Policy Engine + Warn/Redact/Block + Audit Log
- ✅ **เฟส 3 (Endpoint):** **Endpoint Agent** — สแกนไฟล์ในเครื่อง (`agent/file_scanner.py`) + เฝ้าคลิปบอร์ดนอกเบราว์เซอร์ (`agent/clipboard_guard.py`) + Fingerprint + Vision (ผ่าน AI)
- ⏳ **เฟส 4 (Enterprise):** Cloud Connector, SSO, SIEM Integration — โครงต่อยอดพร้อม

## ⚖️ PDPA / ความเป็นส่วนตัว

- ค่าเริ่มต้น **ไม่เก็บเนื้อหาลับฉบับเต็ม** — เก็บเฉพาะ metadata ของเหตุการณ์ (ปรับด้วย `SENTINEL_STORE_CONTENT`)
- Fingerprint เก็บเฉพาะ **ค่า hash** ไม่เก็บข้อความต้นฉบับ
- คัดกรองชั้นแรกทำ **ในเครื่อง** เรียก AI เฉพาะเมื่อจำเป็น
- โมดูล Coaching เน้น "ป้องกัน ไม่ใช่จับผิด" — แนะนำปรึกษา DPO ก่อนใช้งานจริง

---

*เอกสารต้นฉบับแนวคิด: SentinelAI v1.0 • สร้างระบบให้ใช้งานจริงด้วย BytePlus ModelArk*
