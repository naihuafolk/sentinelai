"""
PolicyEngine (โมดูล M3) — แปลงผลการจัดประเภท + บริบท → การกระทำ
กฎ: ใคร (department) / ข้อมูลประเภทใด (label, category) / ช่องทางใด (channel)
     → ทำอย่างไร (Monitor/Warn/Redact/Block)
เลือกกฎที่ priority น้อยสุดที่ "เข้าเงื่อนไข" เป็นตัวตัดสิน
"""
from __future__ import annotations

from typing import Optional

from ..config import settings
from ..schemas import Action, Classification, Label, PolicyMatch
from . import db_bridge as store

_LABEL_ORDER = {Label.PUBLIC: 0, Label.INTERNAL: 1, Label.CONFIDENTIAL: 2, Label.RESTRICTED: 3}


class Decision:
    def __init__(self, action: Action, match: PolicyMatch, require_approval: bool, coaching: str):
        self.action = action
        self.match = match
        self.require_approval = require_approval
        self.coaching = coaching


def _norm(s: str) -> str:
    return (s or "").strip().lower()


class PolicyEngine:
    def evaluate(
        self, cls: Classification, *, channel: str, department: str, org_id: int = 1
    ) -> Decision:
        policies = store.get_policies(org_id)  # เรียงตาม priority แล้ว
        dept = _norm(department)
        chan = _norm(channel)
        cats = {_norm(c) for c in cls.categories}
        # เพิ่มหมวดจาก detections (เผื่อ categories ยังไม่ครบ)
        cats |= {_norm(d.category) for d in cls.detections}

        for pol in policies:
            if not pol.get("enabled", True):
                continue
            r = pol["rule"]
            # ---- ตรวจเงื่อนไข ----
            if r.get("min_label"):
                if _LABEL_ORDER[cls.label] < _LABEL_ORDER[Label(r["min_label"])]:
                    continue
            if r.get("min_risk", 0) and cls.risk_score < int(r["min_risk"]):
                continue
            need_cats = {_norm(c) for c in r.get("categories_any", []) if c}
            if need_cats and not (need_cats & cats):
                continue
            chans = {_norm(c) for c in r.get("channels", []) if c}
            if chans and chan not in chans:
                continue
            depts = {_norm(d) for d in r.get("departments", []) if d}
            if depts and dept not in depts:
                continue

            # ---- เข้าเงื่อนไข → ตัดสิน ----
            action = Action(r.get("action", Action.WARN.value))
            return Decision(
                action=action,
                match=PolicyMatch(
                    policy_id=pol.get("id"),
                    policy_name=pol.get("name", "policy"),
                    matched_rule=r.get("name", ""),
                ),
                require_approval=bool(r.get("require_approval", False)),
                coaching=r.get("coaching", "") or _default_coaching(action, cls),
            )

        # ---- ไม่มีนโยบายเข้าเงื่อนไข ----
        if cls.risk_score <= 15 and cls.label == Label.PUBLIC:
            action = Action.ALLOW
        else:
            action = Action(settings.default_mode) if settings.default_mode in {
                "monitor", "warn", "redact", "block"} else Action.MONITOR
        return Decision(
            action=action,
            match=PolicyMatch(policy_name="default", matched_rule="fallback"),
            require_approval=False,
            coaching=_default_coaching(action, cls),
        )


def _default_coaching(action: Action, cls: Classification) -> str:
    if action in {Action.ALLOW, Action.MONITOR}:
        return ""
    if action == Action.BLOCK:
        return "การส่งข้อมูลนี้ออกนอกองค์กรถูกจำกัดตามนโยบายบริษัท"
    if action == Action.REDACT:
        return "ระบบปิดบังส่วนที่เป็นข้อมูลลับให้แล้ว ส่วนที่เหลือส่งต่อได้"
    return "เนื้อหานี้อาจมีข้อมูลลับ โปรดตรวจสอบก่อนส่งไปยัง AI สาธารณะ"


_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
    return _engine
