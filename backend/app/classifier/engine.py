"""
ClassificationEngine — รวม 3 เทคนิคเข้าด้วยกัน (ตามหัวข้อ 7 ของเอกสาร)
  1) Pattern/Regex   (เร็ว, ในเครื่อง, high-precision ด้วย checksum)
  2) Fingerprinting  (จับเอกสารลับที่ถูกคัดลอกบางส่วน)
  3) AI Semantic     (BytePlus — เข้าใจความหมาย/บริบท/ภาพ, หลายภาษา)

หลักการรวมผล:
  - "Hard detections" (เช่น API key, บัตร ปชช. ที่ผ่าน checksum) = พื้น (floor)
    ของความเสี่ยง/ระดับ — AI ลดต่ำกว่านี้ไม่ได้ (กัน False Negative)
  - "Soft signals" (คีย์เวิร์ด, อีเมล, เบอร์) = ให้ AI ช่วยกลั่นกรอง (ลด False Positive)
  - เรียก AI เฉพาะเคสเสี่ยง/มีภาพ/เข้าข่าย เพื่อคุมต้นทุนและความหน่วง
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ..config import settings
from ..schemas import Classification, Detection, Label
from . import patterns as P
from .fingerprint import get_index
from .semantic import classify_semantic

log = logging.getLogger("sentinel.engine")

_LABEL_ORDER = {Label.PUBLIC: 0, Label.INTERNAL: 1, Label.CONFIDENTIAL: 2, Label.RESTRICTED: 3}
_LABEL_FROM_STR = {l.value.lower(): l for l in Label}

# ชนิดที่ถือเป็น "หลักฐานแข็ง" (ผ่าน validator/precision สูง) → ตั้งพื้นความเสี่ยง
HARD_TYPES = {
    "aws_access_key", "google_api_key", "openai_key", "anthropic_key",
    "slack_token", "github_token", "jwt", "private_key",
    "generic_secret_assign", "db_connection",
    "thai_national_id", "credit_card", "thai_passport",
}


def _max_label(labels: list[Label]) -> Label:
    if not labels:
        return Label.PUBLIC
    return max(labels, key=lambda l: _LABEL_ORDER[l])


def _combine(weights: list[int], decay: float = 0.5) -> int:
    """รวมน้ำหนักหลายชิ้นแบบ diminishing returns, เพดาน 100."""
    if not weights:
        return 0
    ws = sorted(weights, reverse=True)
    total = 0.0
    for i, w in enumerate(ws):
        total += w * (decay ** i)
    return int(min(100, round(total)))


class ClassificationEngine:
    def __init__(self) -> None:
        self.index = get_index()

    # ---- ชั้น 1: Regex/Pattern ----------------------------------------
    def _scan_patterns(self, text: str) -> list[Detection]:
        found: list[Detection] = []
        occupied: list[tuple[int, int]] = []  # กันซ้อนทับ (เช่น เลข 13 หลักซ้อนกับ Luhn)

        for pat in P.PATTERNS:
            for m in pat.regex.finditer(text):
                raw = m.group(0)
                if pat.validator and not pat.validator(raw):
                    continue
                span = (m.start(), m.end())
                if any(not (span[1] <= a or span[0] >= b) for a, b in occupied):
                    continue  # ทับกับที่เจอแล้ว
                occupied.append(span)
                masked = pat.mask(raw) if pat.mask else P.mask_middle(raw)
                found.append(Detection(
                    type=pat.type, category=pat.category, label=pat.label,
                    value_masked=masked, span=span, weight=pat.weight, engine="regex",
                ))

        # สัญญาณคีย์เวิร์ด (soft) — ช่วยบอกบริบท
        for name, cat, label, weight, rx in P.KEYWORD_SIGNALS:
            m = rx.search(text)
            if m:
                found.append(Detection(
                    type=f"signal:{name}", category=cat, label=label,
                    value_masked=m.group(0)[:40], span=(m.start(), m.end()),
                    weight=weight, engine="regex",
                ))
        return found

    # ---- ชั้น 2: Fingerprint ------------------------------------------
    def _scan_fingerprint(self, text: str, org_id: int = 1) -> list[Detection]:
        dets: list[Detection] = []
        for hit in self.index.match(text, org_id=org_id):
            weight = int(hit.similarity * 90)
            dets.append(Detection(
                type=f"fingerprint:{hit.name}", category="business", label=hit.label,
                value_masked=f"{hit.name} (คล้าย {int(hit.similarity*100)}%)",
                span=(0, 0), weight=weight, engine="fingerprint",
            ))
        return dets

    # ---- Orchestration -------------------------------------------------
    async def classify(
        self,
        text: str,
        *,
        images: Optional[list[str]] = None,
        force_ai: Optional[bool] = None,
        org_id: int = 1,
    ) -> Classification:
        text = text or ""
        images = images or []

        regex_dets = self._scan_patterns(text)
        fp_dets = self._scan_fingerprint(text, org_id=org_id)
        all_local = regex_dets + fp_dets

        hard = [d for d in all_local if d.type in HARD_TYPES or d.engine == "fingerprint"]
        regex_all_risk = _combine([d.weight for d in all_local])
        hard_floor = _combine([d.weight for d in hard])
        local_labels = [d.label for d in all_local]

        # เรียก AI เมื่อไร: มีภาพ / มีสัญญาณเสี่ยงพอ / มี fingerprint / บังคับ
        soft_present = any(d.type.startswith("signal:") for d in regex_dets)
        should_ai = (
            settings.ai_enabled and (
                force_ai is True
                or bool(images)
                or bool(fp_dets)
                or regex_all_risk >= settings.ai_risk_threshold
                or soft_present
            )
        )
        if force_ai is False:
            should_ai = False

        ai = None
        if should_ai:
            hint = ", ".join(sorted({d.type for d in all_local})) or "ไม่มีสัญญาณจาก Regex"
            ai = await classify_semantic(text, images=images, hint=hint)

        # ---- รวมผล ----
        engine_tag = "regex"
        reasons: list[str] = []
        categories: set[str] = set()
        ai_used = False
        ai_summary = None

        for d in all_local:
            categories.add(d.category)
        # เหตุผลจาก detections (unique, อ่านง่าย)
        seen_reason: set[str] = set()
        for pat in P.PATTERNS:
            if any(d.type == pat.type for d in regex_dets) and pat.reason_th not in seen_reason:
                reasons.append(pat.reason_th)
                seen_reason.add(pat.reason_th)
        for name, cat, label, weight, rx in P.KEYWORD_SIGNALS:
            if any(d.type == f"signal:{name}" for d in regex_dets):
                r = f"พบคำ/บริบทบ่งชี้ข้อมูล{_cat_th(cat)}"
                if r not in seen_reason:
                    reasons.append(r)
                    seen_reason.add(r)
        for d in fp_dets:
            reasons.append(f"เนื้อหาตรงกับเอกสารลับ: {d.value_masked}")

        ai_detections: list[Detection] = []
        if ai and ai.used:
            ai_used = True
            engine_tag = "combined" if all_local else "ai"
            ai_summary = ai.summary
            for c in ai.categories:
                categories.add(c)
            for r in ai.reasons:
                if r not in seen_reason:
                    reasons.append(f"AI: {r}")
                    seen_reason.add(r)
            # แปลงสิ่งที่ AI เจอ (รวม Vision) เป็น detection ให้แสดงผลได้
            for it in ai.items:
                it_label = _LABEL_FROM_STR.get(str(it.get("label", "")).lower(), Label.CONFIDENTIAL)
                ai_detections.append(Detection(
                    type=f"ai:{it.get('type', 'sensitive')}",
                    category=str(it.get("category", "business")),
                    label=it_label,
                    value_masked=str(it.get("evidence_th") or it.get("evidence") or it.get("type", "ข้อมูลลับ"))[:60],
                    span=(0, 0), weight=0, engine="ai",
                ))
                categories.add(str(it.get("category", "business")))

        # ---- คะแนนความเสี่ยง + ระดับ ----
        if ai_used:
            if hard:  # มีหลักฐานแข็ง → AI ยกได้ ลดต่ำกว่าพื้นไม่ได้
                risk = max(hard_floor, ai.risk_score, regex_all_risk)
                label = _max_label(local_labels + [ai.label])
            elif fp_dets:
                risk = max(regex_all_risk, ai.risk_score)
                label = _max_label(local_labels + [ai.label])
            else:
                # มีแต่ soft signals → เชื่อ AI เป็นหลัก (กัน False Positive)
                risk = max(ai.risk_score, min(regex_all_risk, 40))
                label = _max_label([ai.label] + ([Label.INTERNAL] if soft_present else [Label.PUBLIC]))
        else:
            risk = regex_all_risk
            label = _max_label(local_labels)
            engine_tag = "fingerprint" if (fp_dets and not regex_dets) else "regex"

        # ปรับ label ให้สอดคล้องกับ risk ขั้นต่ำ (กันเคส label สูงแต่ risk ต่ำผิดปกติ)
        if risk >= 76:
            label = _max_label([label, Label.CONFIDENTIAL])
        # Fail-safe: มีรูปแนบมาแต่ AI อ่านไม่สำเร็จ → ห้ามปล่อยผ่านเงียบ ๆ (กันรูปข้อมูลลับหลุด)
        image_unverified = bool(images) and not ai_used
        if image_unverified:
            risk = max(risk, 38)  # ระดับ "warn" — แจ้งเตือนให้ผู้ใช้ตรวจภาพเอง
            label = _max_label([label, Label.INTERNAL])
            reasons = ["⚠️ ตรวจรูปด้วย AI ไม่สำเร็จชั่วคราว — กันไว้ก่อน โปรดตรวจสอบภาพเอง"] + reasons
            engine_tag = "failsafe"
        elif not all_local and not ai_used:
            label, risk = Label.PUBLIC, 0

        return Classification(
            label=label,
            risk_score=int(max(0, min(100, risk))),
            categories=sorted(categories),
            detections=all_local + ai_detections,
            reasons=reasons[:8] or (["ไม่พบข้อมูลลับ"] if risk == 0 else []),
            engine=engine_tag,
            ai_used=ai_used,
            ai_summary=ai_summary,
        )


def _cat_th(cat: str) -> str:
    return {
        "financial": "การเงิน", "pii": "ส่วนบุคคล (PII)", "secret": "ความลับทางเทคนิค",
        "legal": "สัญญา/กฎหมาย", "code": "ซอร์สโค้ด", "business": "ธุรกิจ/กลยุทธ์",
        "general": "ทั่วไป",
    }.get(cat, cat)


_engine: Optional[ClassificationEngine] = None


def get_engine() -> ClassificationEngine:
    global _engine
    if _engine is None:
        _engine = ClassificationEngine()
    return _engine
