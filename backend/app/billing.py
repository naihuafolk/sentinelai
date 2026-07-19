"""
billing.py — ระบบจ่ายเงินอัตโนมัติด้วย Stripe (subscription รายเครื่อง/เดือน)

ออกแบบให้ "ปลอดภัยเสมอ": ถ้าไม่ตั้ง STRIPE_SECRET_KEY → ระบบปิดจ่ายเงินอัตโนมัติเงียบ ๆ
และยังเปิด/ปิด license แบบ manual ผ่าน Super Admin ได้ตามเดิม

โฟลว์:
  ลูกค้าเลือกแพ็กเกจ+จำนวนเครื่อง → Stripe Checkout → จ่าย →
  Stripe ยิง webhook กลับมา → เราตั้ง org เป็น active + seat + วันหมดอายุ อัตโนมัติ
  ต่ออายุอัตโนมัติทุกเดือน (invoice.paid) · ยกเลิก → suspended
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from . import db
from .config import settings

log = logging.getLogger("sentinel.billing")

try:
    import stripe  # type: ignore
    _HAS_STRIPE = True
except Exception:  # pragma: no cover
    stripe = None
    _HAS_STRIPE = False


def enabled() -> bool:
    return bool(_HAS_STRIPE and settings.stripe_secret_key)


def _init() -> None:
    if not enabled():
        raise RuntimeError("ระบบจ่ายเงินยังไม่เปิด (ยังไม่ได้ตั้ง STRIPE_SECRET_KEY)")
    stripe.api_key = settings.stripe_secret_key


def _plans() -> dict:
    # plan -> (Stripe price id [per-seat/เดือน], โควตา/เดือน, ชื่อ)
    return {
        "starter":  {"price": settings.stripe_price_starter,  "quota": 2000,  "name": "Starter"},
        "business": {"price": settings.stripe_price_business, "quota": 20000, "name": "Business"},
    }


def plans_public() -> list[dict]:
    """แพ็กเกจที่พร้อมขาย (ตั้ง price id ใน Stripe แล้ว) สำหรับ UI."""
    return [{"key": k, "name": p["name"], "quota": p["quota"]}
            for k, p in _plans().items() if p["price"]]


def _iso(ts) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


def _sub_qty(sub) -> Optional[int]:
    try:
        return int(sub["items"]["data"][0]["quantity"])
    except Exception:
        return None


def create_checkout(org: dict, plan: str, seats: int, email: str) -> str:
    """สร้าง Stripe Checkout Session คืน URL ให้ redirect ไปจ่าย."""
    _init()
    p = _plans().get(plan)
    if not p or not p["price"]:
        raise ValueError("ไม่พบแพ็กเกจ หรือยังไม่ได้ตั้งราคาใน Stripe")
    seats = max(1, int(seats))
    cust = org.get("stripe_customer_id")
    if not cust:
        c = stripe.Customer.create(email=email or None, name=org.get("name") or None,
                                   metadata={"org_id": str(org["id"])})
        cust = c.id
        db.set_stripe_ids(org["id"], customer_id=cust)
    base = settings.public_base_url
    sess = stripe.checkout.Session.create(
        mode="subscription",
        customer=cust,
        line_items=[{"price": p["price"], "quantity": seats}],
        success_url=base + "/?billing=success",
        cancel_url=base + "/?billing=cancel",
        allow_promotion_codes=True,
        metadata={"org_id": str(org["id"]), "plan": plan, "seats": str(seats)},
        subscription_data={"metadata": {"org_id": str(org["id"]), "plan": plan}},
    )
    return sess.url


def customer_portal(org: dict) -> str:
    """เปิด Stripe Customer Portal (จัดการ/ยกเลิก/อัปเดตบัตร)."""
    _init()
    cust = org.get("stripe_customer_id")
    if not cust:
        raise ValueError("ยังไม่มีข้อมูลการชำระเงิน")
    s = stripe.billing_portal.Session.create(customer=cust, return_url=settings.public_base_url + "/")
    return s.url


def _apply_active(org_id: int, plan: str, seats: int, valid_until: Optional[str], sub_id: Optional[str]) -> None:
    quota = _plans().get(plan, {}).get("quota", 2000)
    db.update_org_license(org_id, plan=plan, seats=seats, status="active",
                          quota_month=quota, valid_until=valid_until)
    if sub_id:
        db.set_stripe_ids(org_id, subscription_id=sub_id)
    log.info("billing: org %s -> active plan=%s seats=%s until=%s", org_id, plan, seats, valid_until)


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """รับ webhook จาก Stripe (ตรวจลายเซ็นก่อนเสมอ) แล้วอัปเดต license."""
    _init()
    if not settings.stripe_webhook_secret:
        raise RuntimeError("ยังไม่ได้ตั้ง STRIPE_WEBHOOK_SECRET")
    event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    typ = event["type"]
    obj = event["data"]["object"]

    if typ == "checkout.session.completed":
        md = obj.get("metadata") or {}
        org_id = int(md.get("org_id", 0) or 0)
        plan = md.get("plan", "starter")
        seats = int(md.get("seats", 1) or 1)
        sub_id = obj.get("subscription")
        valid_until = None
        if sub_id:
            sub = stripe.Subscription.retrieve(sub_id)
            valid_until = _iso(sub.get("current_period_end"))
            seats = _sub_qty(sub) or seats
        if org_id:
            _apply_active(org_id, plan, seats, valid_until, sub_id)

    elif typ in ("invoice.paid", "invoice.payment_succeeded"):
        cust = obj.get("customer")
        org = db.get_org_by_stripe_customer(cust) if cust else None
        if org:
            sub_id = obj.get("subscription")
            plan = org.get("plan", "starter")
            seats = org.get("seats")
            valid_until = None
            if sub_id:
                sub = stripe.Subscription.retrieve(sub_id)
                valid_until = _iso(sub.get("current_period_end"))
                seats = _sub_qty(sub) or seats
                plan = (sub.get("metadata") or {}).get("plan", plan)
            _apply_active(org["id"], plan, seats, valid_until, sub_id)

    elif typ == "customer.subscription.deleted":
        cust = obj.get("customer")
        org = db.get_org_by_stripe_customer(cust) if cust else None
        if org:
            db.update_org_license(org["id"], status="suspended")
            log.info("billing: org %s -> suspended (subscription canceled)", org["id"])

    return {"received": True, "type": typ}
