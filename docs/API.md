# SentinelAI — API Reference

Base URL: `http://127.0.0.1:8000` • API prefix: `/api/v1`
เอกสาร interactive (Swagger): **http://127.0.0.1:8000/docs**

---

## Core

### `POST /api/v1/inspect`
หัวใจของระบบ — ตรวจเนื้อหาที่กำลังจะส่งไป AI แล้วตัดสินการกระทำ

**Request**
```json
{
  "text": "งบการเงินภายในยังไม่ประกาศ กำไรสุทธิ 214 ล้าน",
  "channel": "chatgpt",
  "destination_url": "https://chatgpt.com/",
  "action_type": "paste",
  "user": "somchai.k@company.co.th",
  "department": "การเงิน",
  "device": "FIN-PC-014",
  "images": [],
  "dry_run": false
}
```

**Response**
```json
{
  "decision": "block",
  "classification": {
    "label": "Restricted",
    "risk_score": 88,
    "categories": ["financial"],
    "detections": [
      {"type":"signal:financial_internal","category":"financial","label":"Confidential",
       "value_masked":"งบการเงิน","span":[0,9],"weight":35,"engine":"regex"}
    ],
    "reasons": ["พบคำ/บริบทบ่งชี้ข้อมูลการเงิน"],
    "engine": "regex",
    "ai_used": false,
    "ai_summary": null
  },
  "redacted_text": null,
  "policy": {"policy_id": 2, "policy_name": "Restricted → เว็บ AI สาธารณะ = บล็อก", "matched_rule": "block-restricted-public-ai"},
  "coaching": "ข้อมูลระดับ 'ลับที่สุด' ห้ามออกนอกองค์กร...",
  "event_id": "a1b2c3...",
  "latency_ms": 3
}
```

- `decision`: `allow` | `monitor` | `warn` | `redact` | `block`
- `channel`: `chatgpt|gemini|claude|copilot|deepseek|grok|perplexity|other`
- `images`: array ของ data URI (`data:image/png;base64,...`) สำหรับ Vision (ต้องเปิด AI)

### `POST /api/v1/classify`
จัดประเภทอย่างเดียว ไม่บันทึก Log (สำหรับ Simulator)
```json
{ "text": "...", "channel": "chatgpt", "department": "", "use_ai": null }
```
→ `{ "classification": {...}, "redacted_text": "...", "latency_ms": 5 }`
(`use_ai`: `true` บังคับใช้ AI, `false` ปิด, `null` ตามค่าระบบ)

---

## Audit / Analytics

| Method | Path | รายละเอียด |
|---|---|---|
| GET | `/api/v1/events` | `?page&page_size&decision&channel&department&label&search` → `{items, total, page, page_size}` |
| GET | `/api/v1/events.csv` | ดาวน์โหลด Audit Log เป็น CSV (รายงาน PDPA/ISO) |
| GET | `/api/v1/stats` | สถิติ 30 วัน + trend 14 วัน สำหรับ Dashboard |

---

## Policies (M3)

| Method | Path | รายละเอียด |
|---|---|---|
| GET | `/api/v1/policies` | รายการนโยบาย (เรียงตาม priority) |
| POST | `/api/v1/policies` | สร้างนโยบายใหม่ |
| PUT | `/api/v1/policies/{id}` | แก้ไข |
| DELETE | `/api/v1/policies/{id}` | ลบ |

**Policy Rule** — เงื่อนไข (ค่าว่าง = ไม่สนใจ) → การกระทำ
```json
{
  "name": "block-restricted",
  "min_label": "Restricted",
  "categories_any": ["secret","pii"],
  "channels": ["chatgpt","gemini"],
  "departments": ["การเงิน"],
  "min_risk": 0,
  "action": "block",
  "require_approval": false,
  "coaching": "ข้อความให้ความรู้พนักงาน"
}
```

---

## Fingerprints (M1)

| Method | Path | รายละเอียด |
|---|---|---|
| GET | `/api/v1/fingerprints` | รายการเอกสารลับที่ลงทะเบียน |
| POST | `/api/v1/fingerprints` | **multipart/form-data**: `name`, `label`, `text` และ/หรือ `file` |
| DELETE | `/api/v1/fingerprints/{id}` | ลบ |

> เก็บเฉพาะ **ค่า hash (fingerprint)** ไม่เก็บเนื้อหาดิบ

---

## System

| Method | Path | รายละเอียด |
|---|---|---|
| GET | `/api/v1/config` | ค่าสาธารณะสำหรับ extension (ช่องทางที่เฝ้า, สถานะ AI, model IDs) |
| GET | `/api/v1/health` | `?check_ai=true` เพื่อทดสอบเรียก BytePlus จริง |
| POST | `/api/v1/admin/seed-demo` | ใส่ข้อมูลตัวอย่าง (14 วัน + เอกสารลับ) |

---

## Labels & Actions

**ระดับชั้นความลับ:** `Public` → `Internal` → `Confidential` → `Restricted`
**การกระทำ:** `allow` (ผ่าน) · `monitor` (บันทึก) · `warn` (เตือน) · `redact` (ปิดบัง) · `block` (ห้ามส่ง)
