"""
sms.py — ส่ง SMS แจ้งเตือน "Lead ใหม่" (ฟอร์มติดต่อทีมงาน) ผ่าน Twilio

ออกแบบให้ best-effort: ถ้ายังไม่ตั้งค่า Twilio หรือส่งไม่สำเร็จ จะไม่ throw
(Lead ถูกเก็บลง DB เสมออยู่แล้ว — SMS เป็นแค่การแจ้งเตือนเสริม)
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("sentinel.sms")


async def send_sms(to: str, body: str) -> tuple[bool, str]:
    if not settings.sms_enabled:
        return False, "ยังไม่ได้ตั้งค่า Twilio (SMS)"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Messages.json"
    data = {"From": settings.twilio_from, "To": to, "Body": body[:640]}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, data=data, auth=(settings.twilio_sid, settings.twilio_token))
        if resp.status_code < 300:
            return True, "ok"
        return False, f"Twilio {resp.status_code}: {resp.text[:300]}"
    except Exception as e:  # network/timeout
        return False, str(e)


async def notify_lead(lead: dict[str, Any]) -> None:
    """แจ้งเตือน Lead ใหม่เข้าเบอร์ที่ตั้งไว้ (LEAD_NOTIFY_PHONE). ไม่ throw."""
    try:
        body = (
            "[SentinelAI] มี Lead ใหม่\n"
            f"ชื่อ: {lead.get('name', '')}\n"
            f"ธุรกิจ: {lead.get('business', '')}\n"
            f"เครื่อง: {lead.get('seats', '')}\n"
            f"ติดต่อกลับ: {lead.get('contact', '')}"
        )
        ok, detail = await send_sms(settings.lead_notify_phone, body)
        if not ok:
            log.info("lead SMS not sent: %s", detail)
    except Exception as e:  # pragma: no cover
        log.warning("notify_lead error: %s", e)
