"""
ratelimit.py — จำกัดอัตราแบบ in-memory (เหมาะกับ 1 worker/SQLite)
ใช้กันสแปมฟอร์มติดต่อ, เดารหัสผ่าน, และคุมจำนวน SMS ต่อชั่วโมง
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

_hits: dict[str, deque] = defaultdict(deque)
_sms: deque = deque()


def allow(key: str, limit: int, window_sec: int) -> bool:
    """คืน True ถ้ายังไม่เกิน limit ครั้งใน window_sec วินาที (นับรวมครั้งนี้)."""
    now = time.monotonic()
    dq = _hits[key]
    cutoff = now - window_sec
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    # กันหน่วยความจำโต: เคลียร์คีย์ที่ว่างเป็นครั้งคราว
    if len(_hits) > 5000:
        for k in [k for k, v in _hits.items() if not v]:
            _hits.pop(k, None)
    return True


def sms_allowed(max_per_hour: int) -> bool:
    """เพดานส่ง SMS รวมทั้งระบบต่อชั่วโมง (กันฟอร์มโดนสแปมจนเปลืองเงิน)."""
    now = time.monotonic()
    while _sms and _sms[0] < now - 3600:
        _sms.popleft()
    if len(_sms) >= max_per_hour:
        return False
    _sms.append(now)
    return True
