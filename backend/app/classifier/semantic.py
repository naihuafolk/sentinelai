"""
ชั้นที่ 3: AI Semantic Understanding (BytePlus ModelArk)
เข้าใจ "ความหมาย" ของเนื้อหา — จับข้อมูลลับที่ไม่มีรูปแบบตายตัว เช่น กลยุทธ์ธุรกิจ
ดีลควบรวมกิจการ บทสนทนาลับ และภาพถ่ายหน้าจอ/สลิป/บัตร (Vision/OCR understanding)

ประยุกต์โมเดล reasoning/understanding ที่มีจริงใน ModelArk มาทำหน้าที่ security
(ตามหมายเหตุในเอกสาร: ไม่มีโมเดล guard เฉพาะทาง จึงใช้ reasoning + prompt/นโยบายของเราเอง)
รองรับหลายภาษา (ไทย/อังกฤษ/จีน) ผ่านความสามารถ multilingual ของโมเดลโดยตรง
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..byteplus import get_client
from ..schemas import Label

log = logging.getLogger("sentinel.semantic")

_LABEL_ORDER = {Label.PUBLIC: 0, Label.INTERNAL: 1, Label.CONFIDENTIAL: 2, Label.RESTRICTED: 3}
_LABEL_FROM = {l.value.lower(): l for l in Label}

SYSTEM_PROMPT = """คุณคือ "เครื่องยนต์จัดประเภทข้อมูลลับ" ของระบบ DLP ชื่อ SentinelAI
หน้าที่: วิเคราะห์ข้อความ/ภาพที่พนักงานกำลังจะส่งไปยังเครื่องมือ AI สาธารณะ
แล้วประเมินว่าเป็น "ข้อมูลลับขององค์กร" หรือไม่ ในเชิงความหมาย (ไม่ใช่แค่รูปแบบตายตัว)

จัดระดับ:
- Public: ข้อมูลทั่วไป เผยแพร่ได้ / คำถามความรู้ทั่วไป / โค้ดตัวอย่างสาธารณะ
- Internal: ใช้ภายในองค์กร ไม่ควรหลุด
- Confidential: ลับ จำกัดการเข้าถึง (การเงินภายใน, PII, สัญญา, ซอร์สโค้ดที่มีความลับ)
- Restricted: ลับที่สุด (ดีลควบรวม M&A, ความลับทางการค้า, คีย์ระบบ, งบที่ยังไม่ประกาศ, IP/สูตร/อัลกอริทึมหลัก)

จับข้อมูลลับ "เชิงความหมาย" ที่ Regex จับไม่ได้ โดยเฉพาะ:
- กลยุทธ์ธุรกิจลับ / แผนการตลาดลับ / ดีลควบรวมกิจการ (M&A)
- ทรัพย์สินทางปัญญา: ซอร์สโค้ด/สูตร/อัลกอริทึมหลักของบริษัท (แม้ไม่มีคีย์)
- ข้อมูลการเงินภายในที่ยังไม่ประกาศ / ข้อมูลลูกค้ารายบุคคล
ถ้ามี "ภาพ" แนบมา: อ่านภาพ (OCR) หา บัตรประชาชน/พาสปอร์ต, สลิปโอนเงิน/statement,
หน้าสัญญา/เอกสารลับ, ลายเซ็น — แล้วรายงานว่าเจออะไรในภาพ

ตอบกลับเป็น JSON เท่านั้น:
{
  "label": "Public|Internal|Confidential|Restricted",
  "risk_score": 0-100,
  "categories": ["financial"|"pii"|"secret"|"legal"|"code"|"business"|"general"],
  "is_sensitive": true|false,
  "reasons_th": ["เหตุผลสั้น ๆ ภาษาไทย"],
  "items": [{"type":"business_strategy|mna_deal|source_code_ip|financial_internal|customer_pii|id_card|bank_slip|financial_doc|contract|signature|other","category":"business|financial|pii|secret|legal|code","label":"Confidential|Restricted","evidence_th":"สิ่งที่พบ (ปิดบังค่าจริง)"}],
  "detected_language": "th|en|zh|mixed|other"
}
เกณฑ์ risk_score: Public≈0-15, Internal≈16-40, Confidential≈41-75, Restricted≈76-100"""


@dataclass
class SemanticResult:
    label: Label = Label.PUBLIC
    risk_score: int = 0
    categories: list[str] = field(default_factory=list)
    is_sensitive: bool = False
    reasons: list[str] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)  # สิ่งที่ AI เจอ (รวมภาพ)
    language: str = "unknown"
    used: bool = False
    summary: Optional[str] = None
    error: Optional[str] = None


def _coerce_label(val: str) -> Label:
    return _LABEL_FROM.get(str(val).strip().lower(), Label.PUBLIC)


async def classify_semantic(
    text: str,
    *,
    images: Optional[list[str]] = None,
    hint: str = "",
    max_chars: int = 6000,
) -> SemanticResult:
    """เรียก BytePlus reasoning/vision เพื่อประเมินเชิงความหมาย.

    ถ้าไม่มีคีย์/เรียกไม่สำเร็จ → คืน used=False ให้ engine ใช้เฉพาะผล Regex/Fingerprint.
    """
    client = get_client()
    if not client.enabled:
        return SemanticResult(used=False, error="ai_disabled")

    snippet = text[:max_chars]
    user = f"ข้อความที่ต้องประเมิน:\n---\n{snippet}\n---"
    if hint:
        user += f"\n\nสัญญาณจากชั้นก่อนหน้า (Regex/Fingerprint): {hint}"
    if images:
        user += "\n\n[มีภาพแนบมาด้วย — โปรดอ่าน/เข้าใจภาพ (OCR) เพื่อหาข้อมูลลับ เช่น บัตร ปชช./สลิป/เอกสาร]"

    try:
        data = await client.chat_json(
            SYSTEM_PROMPT, user, images=images, max_tokens=700
        )
    except Exception as e:  # graceful — ระบบยังทำงานต่อด้วยชั้นอื่น
        log.warning("semantic classify failed: %s", e)
        return SemanticResult(used=False, error=str(e))

    if not data:
        return SemanticResult(used=False, error="empty_ai_response")

    label = _coerce_label(data.get("label", "Public"))
    try:
        risk = int(data.get("risk_score", 0))
    except (TypeError, ValueError):
        risk = 0
    risk = max(0, min(100, risk))
    cats = data.get("categories") or []
    if isinstance(cats, str):
        cats = [cats]
    reasons = data.get("reasons_th") or data.get("reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]

    items = data.get("items") or []
    if not isinstance(items, list):
        items = []
    clean_items = [i for i in items if isinstance(i, dict) and i.get("type")]

    return SemanticResult(
        label=label,
        risk_score=risk,
        categories=[str(c) for c in cats],
        is_sensitive=bool(data.get("is_sensitive", risk >= 41)),
        reasons=[str(r) for r in reasons][:5],
        items=clean_items[:8],
        language=str(data.get("detected_language", "unknown")),
        used=True,
        summary=(reasons[0] if reasons else None),
    )
