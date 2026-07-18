"""
auth.py — ระบบสมาชิก/ล็อกอินสำหรับ SaaS (ใช้ stdlib ล้วน ไม่ต้องลงไลบรารีเพิ่ม)
  - แฮชรหัสผ่าน: PBKDF2-HMAC-SHA256
  - โทเคน: JWT-lite (HMAC-SHA256) สำหรับ Dashboard
  - API key ต่อองค์กร: สำหรับ Extension/Agent ส่งเหตุการณ์เข้า org ที่ถูกต้อง
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from . import db
from .config import settings

# ---- secret สำหรับเซ็นโทเคน (persist ข้าม restart) ----
def _get_secret() -> str:
    s = os.getenv("SENTINEL_JWT_SECRET")
    if s:
        return s
    f = settings.base_dir / ".jwt_secret"
    if f.exists():
        return f.read_text().strip()
    s = secrets.token_urlsafe(48)
    try:
        f.write_text(s)
    except Exception:
        pass
    return s


_SECRET = _get_secret()
_TTL = 7 * 24 * 3600  # 7 วัน


# ---- password ----
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---- token (JWT-lite) ----
def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: int, org_id: int, email: str) -> str:
    body = {"uid": user_id, "org": org_id, "email": email, "exp": int(time.time()) + _TTL}
    payload = _b64e(json.dumps(body).encode())
    sig = _b64e(hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    try:
        payload, sig = token.split(".")
        expect = _b64e(hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        body = json.loads(_b64d(payload))
        if body.get("exp", 0) < time.time():
            return None
        return body
    except Exception:
        return None


def new_org_api_key() -> str:
    return "sk_org_" + secrets.token_urlsafe(24)


# ---- FastAPI dependencies ----
async def get_current_user(authorization: str = Header(default="")) -> dict:
    """ตรวจ Bearer token จาก Dashboard -> คืน {user, org}."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "ต้องล็อกอินก่อน")
    body = verify_token(authorization[7:].strip())
    if not body:
        raise HTTPException(401, "โทเคนไม่ถูกต้องหรือหมดอายุ")
    user = db.get_user(body["uid"])
    org = db.get_org(body["org"])
    if not user or not org:
        raise HTTPException(401, "ไม่พบผู้ใช้/องค์กร")
    return {"user": user, "org": org}


async def get_org_from_key(x_sentinel_key: str = Header(default="")) -> dict:
    """ตรวจ API key ขององค์กร (Extension/Agent) -> คืน org.
    ถ้าไม่ส่ง key มา ใช้ default org (id 1) เพื่อความเข้ากันได้กับการใช้งาน local."""
    if x_sentinel_key:
        org = db.get_org_by_api_key(x_sentinel_key.strip())
        if not org:
            raise HTTPException(401, "API key ขององค์กรไม่ถูกต้อง — ยังไม่ได้ซื้อ/ลงทะเบียนกับระบบ")
        return org
    org = db.get_org(1)
    if not org:
        raise HTTPException(500, "ยังไม่ได้ตั้งค่าองค์กรเริ่มต้น")
    return org


# ---- License enforcement (กันเอา API key ไปรันมั่ว) ----
def _now() -> datetime:
    return datetime.now(timezone.utc)


def check_license(org: dict, device_id: str = "") -> None:
    """ตรวจสถานะ license: suspended / หมดอายุ / เกิน seat / เกิน quota.
    ถ้าไม่ผ่าน และ enforce_license=True → 402/403 (บล็อก); ถ้า False → ปล่อยผ่าน."""
    def deny(code: int, msg: str):
        if settings.enforce_license:
            raise HTTPException(code, msg)

    status = (org.get("status") or "trial").lower()
    if status == "suspended":
        deny(403, "องค์กรนี้ถูกระงับการใช้งาน — โปรดติดต่อฝ่ายขาย")
        return
    vu = org.get("valid_until")
    if vu:
        try:
            if datetime.fromisoformat(vu.replace("Z", "+00:00")) < _now():
                deny(402, "License หมดอายุแล้ว — โปรดต่ออายุการใช้งาน")
                return
        except Exception:
            pass
    # quota ต่อเดือน
    quota = int(org.get("quota_month") or 0)
    if quota > 0 and db.org_month_events(org["id"]) >= quota:
        deny(402, f"ใช้ครบโควตาเดือนนี้แล้ว ({quota} ครั้ง) — อัปเกรดแพ็กเกจเพื่อใช้ต่อ")
        return
    # seat (จำนวนอุปกรณ์)
    seats = int(org.get("seats") or 0)
    if seats > 0 and device_id and not db.device_exists(org["id"], device_id):
        if db.count_devices(org["id"]) >= seats:
            deny(402, f"เกินจำนวนอุปกรณ์ที่ซื้อไว้ ({seats} เครื่อง) — เพิ่ม seat เพื่อใช้เครื่องนี้")
            return


def client_ip(request: Request) -> str:
    """ดึงไอพีจริงของ client (อยู่หลัง Caddy/reverse proxy → อ่าน X-Forwarded-For)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    xr = request.headers.get("x-real-ip", "")
    if xr:
        return xr.strip()
    return request.client.host if request.client else ""


def check_device_sharing(org: dict, device_id: str, name: str, share: dict) -> None:
    """กันแชร์คีย์ (1 เครื่อง = 1 สิทธิ์): ถ้าลายนิ้วมือเครื่องเดียวถูกใช้จากหลายไอพีพร้อมกัน
    → แจ้งเตือน (บันทึกเหตุการณ์) และบล็อกถ้า enforce_license."""
    if not share or not share.get("shared"):
        return
    if share.get("newly_flagged"):
        try:
            db.record_license_alert(org["id"], device_id, name, int(share.get("distinct_ips", 0)))
        except Exception:
            pass
    if settings.enforce_license:
        raise HTTPException(
            402,
            f"พบการใช้คีย์นี้จากหลายเครื่อง/ตำแหน่งพร้อมกัน ({share.get('distinct_ips')} ไอพี) "
            "— ผิดเงื่อนไข 1 เครื่อง = 1 สิทธิ์ กรุณาเพิ่มจำนวนเครื่อง (seat) หรือติดต่อฝ่ายขาย")


def is_platform_admin(user: dict) -> bool:
    if not user:
        return False
    if user.get("role") == "platform_admin":
        return True
    if user.get("id") == 1:  # ผู้ตั้งระบบคนแรก = เจ้าของแพลตฟอร์ม
        return True
    return (user.get("email") or "").lower() in settings.admin_email_set()


async def get_platform_admin(authorization: str = Header(default="")) -> dict:
    ctx = await get_current_user(authorization)
    if not is_platform_admin(ctx["user"]):
        raise HTTPException(403, "ต้องเป็นผู้ดูแลแพลตฟอร์ม (Super Admin) เท่านั้น")
    return ctx
