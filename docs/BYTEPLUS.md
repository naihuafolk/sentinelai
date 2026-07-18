# การตั้งค่าโมเดล BytePlus ModelArk

SentinelAI ใช้ **BytePlus ModelArk** เป็นสมองด้านการเข้าใจเชิงความหมาย (ชั้นที่ 3 ของการจัดประเภท)
ModelArk เป็น **OpenAI-compatible** ระบบจึงเรียกผ่านมาตรฐาน `POST /chat/completions` และ `POST /embeddings`

> 📌 ตามที่ระบุในเอกสารคอนเซ็ปต์: ModelArk **ไม่มีโมเดล security/guard เฉพาะทาง** (แบบ Llama Guard)
> SentinelAI จึง **ประยุกต์** โมเดล reasoning/understanding ที่มีจริง ร่วมกับตรรกะ/นโยบายที่เราเขียนเอง
> ส่วนงานกฎตายตัวใช้ Regex/Fingerprint ที่ไม่ต้องพึ่งโมเดล

---

## 1) ขอ API Key

1. สมัคร/เข้าสู่ระบบ [BytePlus Console](https://console.byteplus.com)
2. ไปที่ **ModelArk → API Keys** → สร้างคีย์
3. เปิดใช้ (activate) โมเดลที่ต้องการในเมนู **Models / Endpoints**

## 2) ใส่ค่าใน `backend/.env`

```ini
ARK_API_KEY=your-key-here
ARK_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3   # ap-southeast (มาเลเซีย)

ARK_MODEL_REASONING=seed-2-0-pro-260328        # สมอง Policy Engine (รุ่นล่าสุด Seed 2.0 Pro)
ARK_MODEL_FAST=seed-2-0-lite-260428            # คัดกรองเร็ว (Seed 2.0 Lite)
ARK_MODEL_VISION=seed-2-0-pro-260328           # อ่านภาพ/เอกสาร (multimodal)
ARK_MODEL_EMBEDDING=skylark-embedding-vision-251215   # ฝัง/ค้นความคล้าย (รุ่นล่าสุด)
```

> **สำคัญ:** Model ID เป็นค่าที่เปลี่ยนได้ตามภูมิภาคและบัญชีของคุณ
> ให้เปิดหน้า **Model list** ใน ModelArk แล้วคัดลอก **Model ID / Endpoint** ที่คุณเปิดใช้งานมาใส่แทน
> (ค่าตัวอย่างข้างบนอ้างอิงแคตตาล็อก Seed 1.6 ณ เวลาจัดทำ)

## 3) ตรวจว่าติดตั้งถูก

```bash
# หน้า Dashboard: แท็บ "ระบบ & โมเดล" ต้องขึ้น "เชื่อมต่อ BytePlus ModelArk แล้ว"
curl "http://127.0.0.1:8000/api/v1/health?check_ai=true"
# -> "ark_reachable": true
```

---

## โมเดลแต่ละจุดใช้ทำอะไร (ตามหัวข้อ 8 ของเอกสาร)

| ความสามารถ BytePlus | ใช้ใน SentinelAI | ไฟล์ |
|---|---|---|
| **Reasoning** (Dola/Seed) | สมอง Policy Engine — ประเมินว่าลับจริงไหม + บริบท | `app/classifier/semantic.py` |
| **Vision / Document** | อ่านภาพหน้าจอ/สลิป/บัตร/PDF ที่แนบเข้า AI (OCR) | `semantic.py` (ผ่าน `images=[]`) |
| **Embedding** | fingerprint เชิงความหมาย + ค้นเนื้อหาที่ดัดแปลง | `app/byteplus/client.py` `embed()` |
| **Translation** | ตรวจข้อมูลลับหลายภาษา (ไทย/อังกฤษ/จีน) | ใช้ความสามารถ multilingual ของ reasoning โดยตรง |

## คุมต้นทุน/ความหน่วง

- ชั้น Regex/Fingerprint กรอง **ในเครื่องฟรี** ก่อนเสมอ
- เรียก AI **เฉพาะเคสเสี่ยง** เมื่อคะแนน ≥ `SENTINEL_AI_RISK_THRESHOLD` (ค่าเริ่มต้น 35) หรือมีภาพ/มี fingerprint hit
- ปรับ threshold ให้สูงขึ้น = เรียก AI น้อยลง = ถูกลง (แต่จับเชิงความหมายได้น้อยลง)

## ถ้ายังไม่ใส่คีย์

ระบบ **ทำงานได้ปกติ** ด้วยชั้น Regex + Fingerprint เท่านั้น
`ai_enabled` จะเป็น `false` และ `classification.ai_used` จะเป็น `false` — ไม่มี error
