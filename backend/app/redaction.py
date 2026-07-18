"""
Redaction — ปิดบังเฉพาะส่วนลับ แล้วปล่อยที่เหลือให้ส่งได้ (Action = Redact, โมดูล M4)
ใช้ span จาก Detection ของชั้น Regex/Fingerprint
"""
from __future__ import annotations

from .schemas import Classification, Detection


def redact_text(text: str, classification: Classification) -> str:
    """คืนข้อความที่ปิดบังส่วนที่ตรวจพบแล้ว (เรียงจากท้ายไปหน้าเพื่อไม่ให้ span เพี้ยน)."""
    spans: list[tuple[int, int, str]] = []
    for d in classification.detections:
        start, end = d.span
        if end > start:  # ข้าม fingerprint (span 0,0)
            spans.append((start, end, _placeholder(d)))
    if not spans:
        return text
    spans.sort(key=lambda s: s[0], reverse=True)
    out = text
    for start, end, ph in spans:
        out = out[:start] + ph + out[end:]
    return out


def _placeholder(d: Detection) -> str:
    label = {
        "pii": "ข้อมูลส่วนบุคคล", "financial": "ข้อมูลการเงิน", "secret": "ความลับ",
        "legal": "ข้อมูลสัญญา", "code": "โค้ดลับ", "business": "ข้อมูลธุรกิจ",
    }.get(d.category, "ข้อมูลลับ")
    return f"[ปิดบัง:{label}]"
