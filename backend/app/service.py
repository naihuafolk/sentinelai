"""
Service layer — ประกอบ Interception Flow (หัวข้อ 4 ของเอกสาร):
  จัดประเภท (classify) → ตัดสินตามนโยบาย (policy) → ลงมือ (redact/block) → บันทึก Log
เป็นตัวเชื่อมระหว่าง API routes กับเครื่องยนต์ต่าง ๆ
"""
from __future__ import annotations

import time
import uuid

from . import db
from .classifier import get_engine
from .config import settings
from .policy import get_policy_engine
from .redaction import redact_text
from .rewrite import safe_rewrite
from .schemas import (
    Action, ClassifyOnlyResponse, InspectRequest, InspectResponse, PolicyMatch,
)

_EXCERPT_LEN = 200


async def inspect(req: InspectRequest, org_id: int = 1) -> InspectResponse:
    t0 = time.perf_counter()
    engine = get_engine()
    policy = get_policy_engine()

    cls = await engine.classify(req.text, images=req.images, org_id=org_id)
    decision = policy.evaluate(cls, channel=req.channel, department=req.department, org_id=org_id)
    action = decision.action

    redacted_text = None
    if action == Action.REDACT:
        redacted_text = redact_text(req.text, cls)
        # ปิดบังไม่ได้ (ไม่มี span จับต้องได้ เช่น มาจาก AI/fingerprint ล้วน) และยังเสี่ยงสูง
        if redacted_text == req.text and cls.risk_score >= 41:
            action = Action.BLOCK
            redacted_text = None

    # ---- Safe Rewrite (ปกป้องแต่ไม่ขวางงาน) — เฉพาะเคสที่ AI ทำงานอยู่แล้ว ----
    # (ข้อมูลชัดจาก Regex/fast-path มี redacted_text พอแล้ว ไม่ต้องเรียก AI ช้าซ้ำ = กัน Agent timeout)
    rewrite = None
    if settings.ai_enabled and cls.ai_used and action in (Action.WARN, Action.REDACT, Action.BLOCK) \
            and cls.risk_score >= 30 and not req.dry_run:
        try:
            rewrite = await safe_rewrite(req.text, cls)
        except Exception:
            rewrite = None

    latency_ms = int((time.perf_counter() - t0) * 1000)

    # ---- บันทึก Audit Log (data-minimized) ----
    event_id = uuid.uuid4().hex
    should_log = (not req.dry_run) and (action != Action.ALLOW or cls.risk_score > 0)
    if should_log:
        excerpt = None
        if settings.store_content:
            excerpt = (req.text or "")[:_EXCERPT_LEN]
        db.insert_event({
            "id": event_id,
            "org_id": org_id,
            "ts": db.now_iso(),
            "user": req.user,
            "department": req.department,
            "device": req.device,
            "channel": req.channel,
            "destination_url": req.destination_url,
            "action_type": req.action_type,
            "label": cls.label.value,
            "risk_score": cls.risk_score,
            "categories": cls.categories,
            "decision": action.value,
            "reasons": cls.reasons,
            "policy_name": decision.match.policy_name,
            "ai_used": cls.ai_used,
            "detection_types": sorted({d.type for d in cls.detections}),
            "content_excerpt": excerpt,
        })

    coaching = decision.coaching or None
    return InspectResponse(
        decision=action,
        classification=cls,
        redacted_text=redacted_text,
        safe_rewrite=(rewrite["safe_prompt"] if rewrite else None),
        safe_rewrite_note=(rewrite["note"] if rewrite else None),
        policy=decision.match,
        coaching=coaching,
        event_id=event_id if should_log else None,
        latency_ms=latency_ms,
    )


async def classify_only(text: str, *, use_ai=None, images=None, org_id: int = 1) -> ClassifyOnlyResponse:
    """สำหรับหน้า Simulator/ทดสอบนโยบาย — จัดประเภทอย่างเดียว ไม่บันทึก Log."""
    t0 = time.perf_counter()
    engine = get_engine()
    cls = await engine.classify(text, images=images, force_ai=use_ai, org_id=org_id)
    redacted = redact_text(text, cls)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return ClassifyOnlyResponse(classification=cls, redacted_text=redacted, latency_ms=latency_ms)
