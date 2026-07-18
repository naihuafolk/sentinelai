"""
Audit Log & Analytics (โมดูล M5 + M6)
สร้างสถิติภาพรวมองค์กรจากตาราง events สำหรับ Admin Dashboard
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from . import db
from .config import settings
from .schemas import Stats, TrendPoint

_DETECT_DECISIONS = {"warn", "redact", "block", "monitor"}


def compute_stats(org_id: int = 1, days: int = 30, trend_days: int = 14) -> Stats:
    events = db.all_events_since(org_id, days)

    detections = [e for e in events if e["risk_score"] > 0 or e["decision"] in _DETECT_DECISIONS]
    blocks = [e for e in events if e["decision"] == "block"]
    redactions = [e for e in events if e["decision"] == "redact"]
    warns = [e for e in events if e["decision"] == "warn"]

    by_channel: Counter = Counter()
    by_category: Counter = Counter()
    by_department: Counter = Counter()
    by_label: Counter = Counter()
    for e in detections:
        by_channel[e["channel"] or "other"] += 1
        by_label[e["label"]] += 1
        if e["department"]:
            by_department[e["department"]] += 1
        for c in e["categories"]:
            by_category[c] += 1

    top_department = by_department.most_common(1)[0][0] if by_department else "-"

    # ครอบคลุม Agent: อุปกรณ์ที่ส่งเหตุการณ์เข้ามาใน N วัน
    active_devices = len({e["device"] for e in events if e["device"]})
    if settings.fleet_size > 0:
        active_pct = min(100, round(active_devices / settings.fleet_size * 100))
    else:
        active_pct = 100 if active_devices else 0

    # แนวโน้มรายวัน
    day_det: dict[str, int] = defaultdict(int)
    day_blk: dict[str, int] = defaultdict(int)
    for e in detections:
        d = e["ts"][:10]
        day_det[d] += 1
        if e["decision"] == "block":
            day_blk[d] += 1
    today = datetime.now(timezone.utc).date()
    trend: list[TrendPoint] = []
    for i in range(trend_days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        trend.append(TrendPoint(date=d, detections=day_det.get(d, 0), blocks=day_blk.get(d, 0)))

    return Stats(
        detections_30d=len(detections),
        blocks_30d=len(blocks),
        redactions_30d=len(redactions),
        warns_30d=len(warns),
        top_department=top_department,
        active_agents_pct=active_pct,
        by_channel=dict(by_channel),
        by_category=dict(by_category),
        by_department=dict(by_department),
        by_label=dict(by_label),
        trend=trend,
    )
