# 🖥️ SentinelAI Endpoint Agent — ป้องกันข้อมูลลับ "นอกเบราว์เซอร์"

ส่วนขยายจากฝั่งเบราว์เซอร์ (Extension) มาครอบคลุมช่องทางที่ไม่ผ่านเบราว์เซอร์:
แอป AI เดสก์ท็อป (ChatGPT/Claude/Copilot Desktop), Slack, อีเมล, Word, LINE
และไฟล์ลับที่เก็บอยู่ในเครื่อง

> ใช้ **Python + tkinter** (มากับ Python อยู่แล้ว) — ไม่ต้องติดตั้งไลบรารีเพิ่ม
> ใช้ **เครื่องยนต์ตรวจจับตัวเดียวกับเซิร์ฟเวอร์** และส่งเหตุการณ์เข้า Dashboard เดียวกัน

---

## 1) 📋 Clipboard Guard — เฝ้าคลิปบอร์ดระดับเครื่อง

ดักจับตอน **คัดลอก (Ctrl+C)** ก่อนจะเอาไป **วาง (Ctrl+V)** ลงแอปไหนก็ตาม

| พบข้อมูล | ระบบทำ |
|---|---|
| คีย์/รหัสลับ (Restricted, secret) | ⛔ **ล้างคลิปบอร์ด** — วางไม่ได้ |
| ข้อมูลส่วนบุคคล (PII) | 🛡️ **ปิดบัง** — คลิปบอร์ดเหลือเฉพาะฉบับปิดบัง |
| ข้อมูลลับอื่น (Confidential/Restricted) | ⚠️ **เตือน** — ให้เลือก "ล้างทิ้ง" หรือ "เก็บไว้" |

**รัน:**
```bash
python agent/clipboard_guard.py
```
จะมีหน้าต่างแจ้งเตือนเด้งมุมจอเมื่อพบข้อมูลลับ · กด **Ctrl+C** ในเทอร์มินัลเพื่อหยุด

**ทดสอบแบบไม่เปิดหน้าต่าง:**
```bash
python agent/clipboard_guard.py --selftest "const KEY='sk-proj-abc...'"
```

> รู้ด้วยว่ากำลังจะวางลงแอปไหน (อ่านชื่อหน้าต่างที่โฟกัสบน Windows) — ถ้าเป็นแอป AI จะบันทึกไว้ชัดเจน

---

## 2) 📁 File Scanner — ค้นหาไฟล์ลับในเครื่อง (Data Discovery · M1)

สแกนโฟลเดอร์/ไดรฟ์ ระบุว่าไฟล์ไหน "ลับ" ระดับใด รองรับ: เอกสารข้อความ, ซอร์สโค้ด,
CSV/JSON, และ **PDF** (docx/xlsx ต้องติดตั้งไลบรารีเสริม)

**รัน:**
```bash
python agent/file_scanner.py "C:\Users\me\Documents"
python agent/file_scanner.py . --min-risk 40           # เฉพาะไฟล์เสี่ยงสูง
python agent/file_scanner.py docs --ai                  # ใช้ AI (BytePlus) ประเมินด้วย
python agent/file_scanner.py docs --json report.json    # ออกรายงาน JSON
python agent/file_scanner.py docs --register            # ลงทะเบียนไฟล์ลับเป็น fingerprint
```

`--register` = ทำ "ลายนิ้วมือ" ให้ไฟล์ลับ ครั้งต่อไปถ้าใครคัดลอกเนื้อหาไฟล์นั้นไปวางใน AI
(ผ่านเบราว์เซอร์หรือคลิปบอร์ด) ระบบจะจับได้ทันที แม้คัดลอกเพียงบางส่วน

---

## ⚙️ การตั้งค่า (ไม่บังคับ)

Agent อ่านค่าจาก `backend/.env` และ environment:

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `SENTINEL_BACKEND_URL` | `http://127.0.0.1:8000` | ที่อยู่เซิร์ฟเวอร์ (เพื่อบันทึก Log/Dashboard) |
| `SENTINEL_USER` | ชื่อผู้ใช้ Windows | ผู้ใช้ที่บันทึกในเหตุการณ์ |
| `SENTINEL_DEPARTMENT` | (ว่าง) | แผนก |
| `SENTINEL_DEVICE` | ชื่อเครื่อง | รหัสเครื่อง |

> **ทำงานได้แม้ไม่มีเซิร์ฟเวอร์:** ถ้า backend ไม่ได้เปิด Agent จะใช้เครื่องยนต์ในเครื่อง
> (Regex + Fingerprint) ทันที — ถ้าเปิด backend เหตุการณ์จะไหลเข้า Dashboard ให้เห็นภาพรวมทั้งองค์กร

## 🚀 ให้ทำงานอัตโนมัติตอนเปิดเครื่อง (Windows)

สร้าง Scheduled Task หรือใส่ shortcut ของคำสั่งนี้ในโฟลเดอร์ Startup:
```
pythonw "D:\...\agent\clipboard_guard.py"
```
(`pythonw` = รันเงียบ ๆ ไม่มีหน้าต่างเทอร์มินัล)
