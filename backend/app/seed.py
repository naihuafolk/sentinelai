"""
Seed & bootstrap (multi-tenant)
  - ensure_defaults(): สร้าง org เริ่มต้น (id 1) + โหลด fingerprint ทุก org เข้าดัชนี
  - seed_org_defaults(org_id): ใส่ policy เริ่มต้นให้องค์กรใหม่ (เรียกตอนสมัคร)
  - seed_demo(org_id): ใส่ข้อมูลตัวอย่างให้ Dashboard มีชีวิต
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from . import auth, db
from .classifier.fingerprint import get_index
from .policy import DEFAULT_POLICIES
from .policy.db_bridge import invalidate as invalidate_policies
from .schemas import Label

DEFAULT_ORG_KEY = "sk_org_LOCAL_DEV_DEFAULT_KEY"

SAMPLE_DOCS = [
    {"name": "เทมเพลตสัญญา NDA องค์กร", "label": Label.CONFIDENTIAL.value,
     "text": ("สัญญารักษาความลับ (Non-Disclosure Agreement) ฉบับนี้จัดทำขึ้นระหว่างบริษัทและคู่สัญญา "
              "โดยคู่สัญญาตกลงจะเก็บรักษาข้อมูลอันเป็นความลับทั้งหมด รวมถึงข้อมูลทางการค้า กลยุทธ์ "
              "รายชื่อลูกค้า ราคาต้นทุน และเทคโนโลยี ไว้เป็นความลับ ห้ามเปิดเผยต่อบุคคลภายนอกโดยเด็ดขาด "
              "เว้นแต่ได้รับความยินยอมเป็นลายลักษณ์อักษร การละเมิดข้อตกลงนี้จะมีผลให้ต้องชดใช้ค่าเสียหาย")},
    {"name": "งบการเงินภายใน ไตรมาส 2/2569 (ร่าง ยังไม่ประกาศ)", "label": Label.RESTRICTED.value,
     "text": ("งบการเงินภายในไตรมาส 2 ปี 2569 (ร่าง ยังไม่ประกาศต่อสาธารณะ) รายได้รวม 1,248 ล้านบาท "
              "เพิ่มขึ้นร้อยละ 12 จากช่วงเดียวกันของปีก่อน กำไรสุทธิ 214 ล้านบาท อัตรากำไรขั้นต้นร้อยละ 38 "
              "งบดุลแสดงสินทรัพย์รวม 5,600 ล้านบาท หนี้สินรวม 2,100 ล้านบาท ข้อมูลนี้เป็นความลับสูงสุด "
              "ห้ามเผยแพร่ก่อนการประกาศผลประกอบการอย่างเป็นทางการ")},
]


def load_fingerprints_into_index() -> None:
    idx = get_index()
    idx._docs.clear()
    for fp in db.get_all_fingerprints_full():
        try:
            label = Label(fp["label"])
        except ValueError:
            label = Label.CONFIDENTIAL
        idx.add_hashes(fp["id"], fp["name"], label, set(fp["hashes"]), org_id=fp.get("org_id", 1))


def seed_org_defaults(org_id: int) -> None:
    """ใส่ policy เริ่มต้นให้องค์กร (ถ้ายังไม่มี)."""
    if db.count_policies(org_id) == 0:
        for p in DEFAULT_POLICIES:
            db.insert_policy(org_id, p["name"], p["enabled"], p["priority"], p["rule"])
        invalidate_policies(org_id)


def register_sample_fingerprints(org_id: int = 1) -> None:
    idx = get_index()
    for doc in SAMPLE_DOCS:
        hashes = sorted(idx.compute_hashes(doc["text"]))
        fid, _ = db.insert_fingerprint(org_id, doc["name"], doc["label"], len(hashes), hashes)
        idx.add_hashes(fid, doc["name"], Label(doc["label"]), set(hashes), org_id=org_id)


def ensure_defaults() -> None:
    # สร้างองค์กรเริ่มต้น (id 1) สำหรับใช้งาน local / dev
    if not db.get_org(1):
        db.create_org("องค์กรเริ่มต้น (Local)", DEFAULT_ORG_KEY, plan="enterprise",
                      status="active", seats=9999, quota_month=0)  # quota 0 = ไม่จำกัด
    seed_org_defaults(1)
    load_fingerprints_into_index()


# ---- Demo events ----
_USERS = [("somchai.k", "การเงิน"), ("naree.p", "ขาย"), ("dev.arm", "วิศวกรรม"),
          ("hr.mint", "HR"), ("law.ploy", "กฎหมาย"), ("mkt.tan", "การตลาด"),
          ("fin.oil", "การเงิน"), ("dev.beam", "วิศวกรรม"), ("sale.nan", "ขาย"), ("mkt.fah", "การตลาด")]
_CHANNELS = ["chatgpt", "gemini", "claude", "copilot", "deepseek"]
_SCEN = [
    ("financial", "Restricted", "block", "signal:financial_internal", "พบตัวเลขงบดุล + คำว่า 'ยังไม่ประกาศ'", 88),
    ("pii", "Confidential", "redact", "thai_national_id", "พบเลขบัตรประชาชนไทย 13 หลัก (ผ่าน checksum)", 70),
    ("secret", "Restricted", "block", "openai_key", "พบ OpenAI/LLM API Key", 90),
    ("business", "Internal", "warn", "signal:strategy", "พบคำ/บริบทบ่งชี้ข้อมูลธุรกิจ/กลยุทธ์", 45),
    ("legal", "Confidential", "warn", "fingerprint:เทมเพลตสัญญา NDA องค์กร", "เนื้อหาตรงกับเอกสารลับ NDA", 66),
    ("pii", "Confidential", "redact", "credit_card", "พบหมายเลขบัตรเครดิต (ผ่าน Luhn check)", 75),
    ("business", "Restricted", "block", "signal:mna", "พบบริบทดีลควบรวมกิจการ (M&A)", 82),
    ("pii", "Internal", "monitor", "email", "พบอีเมล", 25),
    ("financial", "Confidential", "warn", "thai_bank_account", "พบรูปแบบเลขบัญชีธนาคาร", 55),
    ("secret", "Confidential", "warn", "generic_secret_assign", "พบการกำหนดค่ารหัสลับ/รหัสผ่าน", 55),
]


def seed_demo(org_id: int = 1, days: int = 14, per_day: tuple[int, int] = (6, 14)) -> int:
    rng = random.Random(2569)
    with db._lock:
        conn = db._connect()
        conn.execute("DELETE FROM events WHERE org_id=?", (org_id,))
        conn.commit()
    count = 0
    now = datetime.now(timezone.utc)
    featured = [
        ("somchai.k", "การเงิน", "chatgpt", "financial", "Restricted", "block", "signal:financial_internal", "พบตัวเลขงบดุล + คำว่า 'ยังไม่ประกาศ'", 88, 24),
        ("naree.p", "ขาย", "gemini", "pii", "Confidential", "redact", "thai_national_id", "พบเลขบัตรประชาชนลูกค้า 13 หลัก", 72, 82),
        ("dev.arm", "วิศวกรรม", "claude", "secret", "Restricted", "block", "openai_key", "พบ API Key ในซอร์สโค้ด", 90, 128),
        ("hr.mint", "HR", "copilot", "business", "Internal", "warn", "signal:classified_marker", "พบเอกสารภายใน (Internal only)", 40, 160),
    ]
    for u, dept, chan, cat, label, dec, dtype, reason, risk, mins in featured:
        _insert_event(org_id, now - timedelta(minutes=mins), u, dept, chan, cat, label, dec, dtype, reason, risk)
        count += 1
    for d in range(days):
        day = now - timedelta(days=d)
        for _ in range(rng.randint(*per_day)):
            user, dept = rng.choice(_USERS)
            chan = rng.choice(_CHANNELS)
            cat, label, dec, dtype, reason, risk = rng.choice(_SCEN)
            ts = day.replace(hour=rng.randint(8, 19), minute=rng.randint(0, 59), second=rng.randint(0, 59))
            _insert_event(org_id, ts, user, dept, chan, cat, label, dec, dtype, reason, risk)
            count += 1
    return count


def _insert_event(org_id, ts, user, dept, chan, cat, label, dec, dtype, reason, risk):
    urls = {"chatgpt": "https://chatgpt.com/", "gemini": "https://gemini.google.com/app",
            "claude": "https://claude.ai/new", "copilot": "https://copilot.microsoft.com/",
            "deepseek": "https://chat.deepseek.com/"}
    db.insert_event({
        "id": uuid.uuid4().hex, "org_id": org_id, "ts": ts.isoformat(timespec="seconds"),
        "user": user, "department": dept, "device": f"{user.split('.')[0].upper()}-PC",
        "channel": chan, "destination_url": urls.get(chan, ""), "action_type": "paste",
        "label": label, "risk_score": risk, "categories": [cat], "decision": dec,
        "reasons": [reason], "policy_name": "demo", "ai_used": risk >= 41,
        "detection_types": [dtype], "content_excerpt": None,
    })
