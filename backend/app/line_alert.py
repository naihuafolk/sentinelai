"""
line_alert.py — แจ้งเตือนเข้า LINE ทันทีเมื่อพบการพยายามส่งข้อมูลลับ

ใช้ LINE Messaging API (push message):
  POST https://api.line.me/v2/bot/message/push
  Authorization: Bearer <channel access token>
  body: {"to": <userId/groupId>, "messages": [{"type":"text","text": ...}]}

ออกแบบให้ "best-effort": ยิงแบบไม่บล็อกการตอบกลับ และไม่ throw ออกไปข้างนอก
(การแจ้งเตือนล้มเหลวต้องไม่ทำให้การตรวจ/ตอบกลับพัง).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from . import db

log = logging.getLogger("sentinel.line")

_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_DECISION_TH = {"block": "⛔ บล็อก", "redact": "🛡️ ปิดบัง", "warn": "⚠️ เตือน", "monitor": "👁️ บันทึก"}


async def _push(token: str, to: str, text: str) -> tuple[bool, str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"to": to, "messages": [{"type": "text", "text": text[:4900]}]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_PUSH_URL, headers=headers, json=body)
        if resp.status_code < 300:
            return True, "ok"
        return False, f"LINE {resp.status_code}: {resp.text[:300]}"
    except Exception as e:  # network/timeout
        return False, str(e)


def _format_event(org: dict, ev: dict[str, Any]) -> str:
    dec = _DECISION_TH.get(ev.get("decision", ""), ev.get("decision", ""))
    reasons = ev.get("reasons") or []
    reason = reasons[0] if reasons else ""
    lines = [
        "🚨 SentinelAI แจ้งเตือนความเสี่ยง",
        f"องค์กร: {org.get('name', '')}",
        f"การตัดสิน: {dec}  (ความเสี่ยง {ev.get('risk_score', 0)}/100)",
    ]
    if ev.get("user"):
        lines.append(f"ผู้ใช้: {ev['user']}")
    if ev.get("department"):
        lines.append(f"แผนก: {ev['department']}")
    if ev.get("channel"):
        lines.append(f"ช่องทาง: {ev['channel']}")
    if reason:
        lines.append(f"เหตุผล: {reason}")
    if ev.get("ts"):
        lines.append(f"เวลา: {ev['ts']}")
    return "\n".join(lines)


async def maybe_alert(org_id: int, ev: dict[str, Any]) -> None:
    """ยิงแจ้งเตือนถ้าองค์กรเปิดใช้ + ความเสี่ยงถึงเกณฑ์. ไม่ throw."""
    try:
        org = db.get_org(org_id)
        if not org or not org.get("alert_enabled"):
            return
        token = (org.get("line_token") or "").strip()
        to = (org.get("line_to") or "").strip()
        if not token or not to:
            return
        if int(ev.get("risk_score", 0)) < int(org.get("alert_min_risk") or 70):
            return
        ok, detail = await _push(token, to, _format_event(org, ev))
        if not ok:
            log.warning("LINE alert failed for org %s: %s", org_id, detail)
    except Exception as e:  # pragma: no cover
        log.warning("LINE alert error: %s", e)


async def send_test(org: dict) -> tuple[bool, str]:
    """ส่งข้อความทดสอบ (ปุ่ม 'ส่งทดสอบ' ในแดชบอร์ด)."""
    token = (org.get("line_token") or "").strip()
    to = (org.get("line_to") or "").strip()
    if not token or not to:
        return False, "ยังไม่ได้ตั้งค่า Token หรือ ID ผู้รับ"
    return await _push(
        token, to,
        f"✅ ทดสอบการแจ้งเตือน SentinelAI สำเร็จ\n"
        f"องค์กร: {org.get('name', '')}\n"
        f"ระบบพร้อมส่งแจ้งเตือนเข้า LINE แล้ว 🛡️",
    )
