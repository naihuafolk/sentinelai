"""
ตัวกลางเข้าถึงนโยบายพร้อมแคชต่อองค์กร (policies ถูกอ่านทุกครั้งที่ /inspect)
เรียก invalidate(org_id) หลังแก้ไขนโยบายของ org นั้น
"""
from __future__ import annotations

from typing import Optional

from .. import db

_cache: dict[int, list[dict]] = {}


def get_policies(org_id: int = 1) -> list[dict]:
    if org_id not in _cache:
        _cache[org_id] = db.get_policies(org_id)
    return _cache[org_id]


def invalidate(org_id: Optional[int] = None) -> None:
    if org_id is None:
        _cache.clear()
    else:
        _cache.pop(org_id, None)
