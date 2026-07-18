"""
ชั้นที่ 2: Fingerprinting
จับ "เอกสารต้นฉบับที่องค์กรระบุว่าลับ" แม้พนักงานจะคัดลอกเพียงบางส่วน/ดัดแปลง

เทคนิค: char n-gram shingling + hashing (ทำงานได้ทุกภาษา รวมทั้งไทยที่ตัดคำยาก)
คำนวณ containment similarity = |A ∩ D| / min(|A|, |D|)
  - ถ้าข้อความที่วางมาบางส่วนถูกลอกจากเอกสารลับ → shingles จะทับกันสูง
ทำงาน "ในเครื่อง" 100% (ไม่ต้องพึ่ง AI); embedding ของ BytePlus เป็นตัวเสริม (semantic).
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from typing import Optional

from ..schemas import Label

SHINGLE = 12  # ความยาว char n-gram


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def shingles(text: str, k: int = SHINGLE) -> set[int]:
    """สร้างชุด hash ของ char n-gram (ใช้ crc32 ให้เบาและเสถียร)."""
    t = normalize(text)
    if len(t) < k:
        return {zlib.crc32(t.encode("utf-8"))} if t else set()
    return {zlib.crc32(t[i : i + k].encode("utf-8")) for i in range(len(t) - k + 1)}


@dataclass
class FingerprintDoc:
    id: int
    name: str
    label: Label
    hashes: set[int]
    org_id: int = 1


@dataclass
class FingerprintHit:
    id: int
    name: str
    label: Label
    similarity: float  # 0..1


class FingerprintIndex:
    """ดัชนีลายนิ้วมือเอกสารลับ (โหลดจาก DB ตอนเริ่ม, อัปเดตเมื่อ register)."""

    def __init__(self) -> None:
        self._docs: list[FingerprintDoc] = []

    def clear(self) -> None:
        self._docs.clear()

    def add(self, id: int, name: str, label: Label, text: str, org_id: int = 1) -> int:
        h = shingles(text)
        self._docs.append(FingerprintDoc(id=id, name=name, label=label, hashes=h, org_id=org_id))
        return len(h)

    def add_hashes(self, id: int, name: str, label: Label, hashes: set[int], org_id: int = 1) -> None:
        """เพิ่มเอกสารจาก hash ที่คำนวณไว้แล้ว (โหลดจาก DB โดยไม่เก็บเนื้อหาดิบ)."""
        self._docs.append(FingerprintDoc(id=id, name=name, label=label, hashes=set(hashes), org_id=org_id))

    def remove(self, id: int, org_id: Optional[int] = None) -> None:
        self._docs = [d for d in self._docs if not (d.id == id and (org_id is None or d.org_id == org_id))]

    def compute_hashes(self, text: str) -> set[int]:
        return shingles(text)

    def match(self, text: str, org_id: int = 1, threshold: float = 0.30) -> list[FingerprintHit]:
        query = shingles(text)
        if not query:
            return []
        hits: list[FingerprintHit] = []
        for doc in self._docs:
            if doc.org_id != org_id or not doc.hashes:
                continue
            inter = len(query & doc.hashes)
            if inter == 0:
                continue
            sim = inter / max(1, min(len(query), len(doc.hashes)))
            if sim >= threshold:
                hits.append(
                    FingerprintHit(id=doc.id, name=doc.name, label=doc.label, similarity=round(sim, 3))
                )
        hits.sort(key=lambda h: h.similarity, reverse=True)
        return hits

    def __len__(self) -> int:
        return len(self._docs)


_index = FingerprintIndex()


def get_index() -> FingerprintIndex:
    return _index
