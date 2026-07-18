"""
ชุดทดสอบแกนระบบ SentinelAI — รันได้ทั้ง `python tests/test_core.py` และ `pytest`
ครอบคลุม: validators, classification 3 ชั้น, การรวมผล AI (mock), redaction, policy
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifier import engine as engine_mod
from app.classifier.engine import get_engine
from app.classifier.fingerprint import get_index
from app.classifier.patterns import validate_luhn, validate_thai_id
from app.classifier.semantic import SemanticResult
from app.config import settings
from app.policy.engine import PolicyEngine
from app.redaction import redact_text
from app.schemas import Action, Classification, Label

_failures = []


def check(name, cond):
    status = "PASS" if cond else "FAIL"
    if not cond:
        _failures.append(name)
    print(f"  [{status}] {name}")


# ---- 1) Validators ------------------------------------------------------
def test_validators():
    print("validators:")
    check("thai_id valid (checksum ok)", validate_thai_id("1101700207366"))
    check("thai_id invalid (bad checksum)", not validate_thai_id("1101700207364"))
    check("thai_id reject all-same", not validate_thai_id("1111111111111"))
    check("luhn valid visa", validate_luhn("4111111111111111"))
    check("luhn invalid", not validate_luhn("4111111111111112"))


# ---- 2) Offline classification (Regex/Fingerprint) ----------------------
def test_offline_classification():
    print("offline classification (no AI):")
    key = settings.ark_api_key
    settings.ark_api_key = ""  # ปิด AI
    eng = get_engine()

    async def run():
        c1 = await eng.classify("ขอสูตรต้มยำกุ้งหน่อยครับ")
        check("harmless -> Public risk 0", c1.label == Label.PUBLIC and c1.risk_score == 0)

        c2 = await eng.classify("API key: sk-proj-abcd1234efgh5678ijkl9012mnop3456qrst")
        check("api key -> Restricted", c2.label == Label.RESTRICTED and c2.risk_score >= 80)
        check("api key detection present", any(d.type == "openai_key" for d in c2.detections))

        c3 = await eng.classify("เลขบัตรประชาชน 1101700207366")
        check("valid thai id detected", any(d.type == "thai_national_id" for d in c3.detections))

        c4 = await eng.classify("เลขบัตรประชาชน 1101700207364")  # checksum ผิด
        check("invalid thai id NOT flagged (no false positive)",
              not any(d.type == "thai_national_id" for d in c4.detections))

    asyncio.run(run())
    settings.ark_api_key = key


# ---- 3) Fingerprint partial-copy ---------------------------------------
def test_fingerprint():
    print("fingerprint (partial copy):")
    idx = get_index()
    idx.add(999, "เอกสารลับทดสอบ", Label.RESTRICTED,
            "โครงการเข้าซื้อกิจการคู่แข่งมูลค่า 3200 ล้านบาท ห้ามเปิดเผยก่อนประกาศอย่างเป็นทางการ")
    hits = idx.match("ช่วยสรุปดีลนี้: เข้าซื้อกิจการคู่แข่งมูลค่า 3200 ล้านบาท ห้ามเปิดเผยก่อนประกาศ")
    check("partial copy matched", len(hits) > 0 and hits[0].similarity >= 0.3)
    check("no match for unrelated text", len(idx.match("วันนี้อากาศดีมากไปเที่ยวทะเลกันเถอะ")) == 0)
    idx.remove(999)


# ---- 4) AI merge logic (mocked BytePlus) --------------------------------
def test_ai_merge():
    print("AI semantic merge (mocked BytePlus):")
    key = settings.ark_api_key
    settings.ark_api_key = "TEST-MOCK-KEY"  # เปิดเส้นทาง AI
    eng = get_engine()
    orig = engine_mod.classify_semantic

    async def run():
        # (ก) AI ยกระดับเนื้อหาเชิงความหมายที่ Regex จับไม่ได้
        async def fake_high(text, images=None, hint="", max_chars=6000):
            return SemanticResult(label=Label.RESTRICTED, risk_score=90, categories=["business"],
                                  is_sensitive=True, reasons=["ดีลควบรวมกิจการลับ"], used=True)
        engine_mod.classify_semantic = fake_high
        c = await eng.classify("โครงการช้างเผือกจะเปลี่ยนอนาคตบริษัทเราไปตลอดกาล", force_ai=True)
        check("AI elevates semantic-only -> Restricted", c.label == Label.RESTRICTED)
        check("AI risk propagated (>=90)", c.risk_score >= 90)
        check("ai_used flag true", c.ai_used is True)

        # (ข) หลักฐานแข็ง (API key) — AI ลดระดับไม่ได้ (กัน False Negative)
        async def fake_low(text, images=None, hint="", max_chars=6000):
            return SemanticResult(label=Label.PUBLIC, risk_score=0, categories=["general"],
                                  is_sensitive=False, reasons=["ดูปลอดภัย"], used=True)
        engine_mod.classify_semantic = fake_low
        c2 = await eng.classify("token = sk-proj-abcd1234efgh5678ijkl9012mnop3456qrst", force_ai=True)
        check("hard evidence floors label at Restricted", c2.label == Label.RESTRICTED)
        check("hard evidence floors risk (>=80)", c2.risk_score >= 80)

    asyncio.run(run())
    engine_mod.classify_semantic = orig
    settings.ark_api_key = key


# ---- 5) Redaction -------------------------------------------------------
def test_redaction():
    print("redaction:")
    key = settings.ark_api_key
    settings.ark_api_key = ""
    eng = get_engine()

    async def run():
        text = "บัตร 1101700207366 บัตรเครดิต 4111 1111 1111 1111"
        c = await eng.classify(text)
        red = redact_text(text, c)
        check("thai id removed from redacted", "1101700207366" not in red)
        check("credit card removed from redacted", "4111 1111 1111 1111" not in red)
        check("redaction marker present", "[ปิดบัง" in red)

    asyncio.run(run())
    settings.ark_api_key = key


# ---- 6) Policy engine ---------------------------------------------------
def test_policy():
    print("policy engine:")
    pe = PolicyEngine()
    import app.policy.db_bridge as bridge
    orig = bridge.get_policies
    bridge.get_policies = lambda org_id=1: [
        {"id": 1, "name": "block-restricted", "enabled": True, "priority": 20,
         "rule": {"name": "r1", "min_label": "Restricted", "categories_any": [], "channels": [],
                  "departments": [], "min_risk": 0, "action": "block", "require_approval": False, "coaching": ""}},
        {"id": 2, "name": "warn-confidential", "enabled": True, "priority": 60,
         "rule": {"name": "r2", "min_label": "Confidential", "categories_any": [], "channels": [],
                  "departments": [], "min_risk": 0, "action": "warn", "require_approval": False, "coaching": ""}},
    ]
    try:
        restricted = Classification(label=Label.RESTRICTED, risk_score=90)
        d = pe.evaluate(restricted, channel="chatgpt", department="การเงิน")
        check("restricted -> block", d.action == Action.BLOCK)

        conf = Classification(label=Label.CONFIDENTIAL, risk_score=60)
        d2 = pe.evaluate(conf, channel="chatgpt", department="ขาย")
        check("confidential -> warn", d2.action == Action.WARN)

        pub = Classification(label=Label.PUBLIC, risk_score=0)
        d3 = pe.evaluate(pub, channel="chatgpt", department="ขาย")
        check("public -> allow (no policy match)", d3.action == Action.ALLOW)
    finally:
        bridge.get_policies = orig


def main():
    print("=" * 60)
    print("SentinelAI — Core Test Suite")
    print("=" * 60)
    test_validators()
    test_offline_classification()
    test_fingerprint()
    test_ai_merge()
    test_redaction()
    test_policy()
    print("=" * 60)
    if _failures:
        print(f"FAILED ({len(_failures)}): {_failures}")
        sys.exit(1)
    print("ALL TESTS PASSED ✓")


if __name__ == "__main__":
    main()
