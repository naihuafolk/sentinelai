"""
Safe Rewrite — ฟีเจอร์เรือธง "ปกป้องแต่ไม่ขวางงาน"
แทนที่จะบล็อกทื่อ ๆ ให้ BytePlus reasoning เขียนคำถามใหม่ที่ตัดข้อมูลลับออก
แต่คงเจตนา/คำถามเดิมไว้ — พนักงานยังได้คำตอบจาก AI โดยข้อมูลลับไม่หลุด

ใช้ได้เมื่อเปิด BytePlus (ARK_API_KEY) เท่านั้น; ถ้าปิดจะคืน None (ระบบยังทำงานปกติ)
"""
from __future__ import annotations

import logging
from typing import Optional

from .byteplus import get_client
from .schemas import Classification

log = logging.getLogger("sentinel.rewrite")

SYSTEM = """คุณคือ "ผู้ช่วยเขียนคำถามใหม่ให้ปลอดภัย" (Safe Prompt Rewriter) ของระบบ DLP ชื่อ SentinelAI
สถานการณ์: พนักงานกำลังจะส่งข้อความไปยัง AI สาธารณะ (ChatGPT ฯลฯ) แต่มีข้อมูลลับขององค์กรปนอยู่

ภารกิจ: เขียนข้อความใหม่ที่
1) ตัด/แทนที่ "ข้อมูลลับจริง" ทุกจุด ด้วยตัวแทน (placeholder) เช่น [ตัวเลข], [ชื่อบริษัท],
   [ชื่อบุคคล], [API_KEY], [เลขบัญชี] — ห้ามคงค่าจริงไว้เด็ดขาด
2) คง "เจตนา/คำถาม" ของผู้ใช้ไว้ครบ เพื่อให้ AI ยังตอบได้เป็นประโยชน์เหมือนเดิม
3) ห้ามแต่งข้อมูลลับขึ้นใหม่ และห้ามเดาค่าจริง

ตัวอย่าง:
เดิม: "ช่วยสรุปงบนี้: บริษัท ก. กำไรสุทธิ 214 ล้านบาท (ยังไม่ประกาศ)"
ใหม่: "ช่วยสรุปงบการเงินนี้: [ชื่อบริษัท] กำไรสุทธิ [ตัวเลข] (ข้อมูลภายใน)"

ตอบกลับเป็น JSON เท่านั้น:
{"safe_prompt": "ข้อความที่ปลอดภัยแล้ว", "changed": true, "note_th": "ตัดอะไรออกบ้าง (สั้น ๆ)"}"""


async def safe_rewrite(text: str, cls: Classification, *, max_chars: int = 4000) -> Optional[dict]:
    """คืน {'safe_prompt','note'} หรือ None ถ้า AI ปิด/ล้มเหลว/ไม่มีอะไรให้แก้."""
    client = get_client()
    if not client.enabled or not text.strip():
        return None
    detected = ", ".join(sorted({d.type for d in cls.detections})) or "ข้อมูลลับ"
    user = f"ข้อความเดิม:\n---\n{text[:max_chars]}\n---\nสิ่งที่ตรวจพบว่าลับ: {detected}"
    try:
        data = await client.chat_json(SYSTEM, user, max_tokens=900)
    except Exception as e:  # graceful
        log.warning("safe_rewrite failed: %s", e)
        return None
    sp = (data.get("safe_prompt") or "").strip()
    if not sp or not data.get("changed", True):
        return None
    # กันพลาด: ถ้าโมเดลคืนข้อความเดิมเป๊ะ ถือว่าไม่ได้แก้
    if sp == text.strip():
        return None
    return {"safe_prompt": sp, "note": (data.get("note_th") or "").strip()}
