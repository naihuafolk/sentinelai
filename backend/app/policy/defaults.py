"""
นโยบายเริ่มต้น — สะท้อนตัวอย่างในหน้า Policy Builder ของเอกสาร (หัวข้อ 9)
priority น้อย = ตรวจก่อน (สำคัญกว่า)
"""
from ..schemas import Action, Label

DEFAULT_POLICIES: list[dict] = [
    {
        "name": "PII ทุกกรณี → ปิดบังอัตโนมัติ",
        "enabled": True, "priority": 10,
        "rule": {
            "name": "auto-redact-pii",
            "categories_any": ["pii"], "channels": [], "departments": [],
            "min_label": None, "min_risk": 0,
            "action": Action.REDACT.value, "require_approval": False,
            "coaching": "พบข้อมูลส่วนบุคคล (PII) ระบบปิดบังให้อัตโนมัติตาม PDPA — "
                        "โปรดหลีกเลี่ยงการส่งข้อมูลบัตรประชาชน/เบอร์/บัญชีของบุคคลไปยัง AI สาธารณะ",
        },
    },
    {
        "name": "Restricted → เว็บ AI สาธารณะ = บล็อก",
        "enabled": True, "priority": 20,
        "rule": {
            "name": "block-restricted-public-ai",
            "min_label": Label.RESTRICTED.value, "categories_any": [],
            "channels": ["chatgpt", "gemini", "claude", "copilot", "deepseek", "grok", "perplexity", "other"],
            "departments": [], "min_risk": 0,
            "action": Action.BLOCK.value, "require_approval": False,
            "coaching": "ข้อมูลระดับ 'ลับที่สุด (Restricted)' ห้ามออกนอกองค์กร — "
                        "หากต้องใช้ AI โปรดใช้ AI ภายในองค์กร (Private/On-Prem) แทน",
        },
    },
    {
        "name": "ความลับทางเทคนิค (Secrets/Keys) → บล็อก",
        "enabled": True, "priority": 25,
        "rule": {
            "name": "block-secrets",
            "categories_any": ["secret"], "channels": [], "departments": [],
            "min_label": None, "min_risk": 0,
            "action": Action.BLOCK.value, "require_approval": False,
            "coaching": "พบคีย์/รหัสลับของระบบ การส่งออกอาจทำให้ระบบถูกเจาะ — "
                        "ให้เพิกถอน (revoke) คีย์ที่หลุด และใช้ตัวแปรแทนค่าเมื่อ debug กับ AI",
        },
    },
    {
        "name": "Confidential + ฝ่ายการตลาด → เตือน + ขออนุมัติ",
        "enabled": True, "priority": 40,
        "rule": {
            "name": "warn-confidential-marketing",
            "min_label": Label.CONFIDENTIAL.value, "categories_any": [],
            "channels": [], "departments": ["การตลาด", "marketing"], "min_risk": 0,
            "action": Action.WARN.value, "require_approval": True,
            "coaching": "ข้อมูลนี้จัดเป็น 'ลับ (Confidential)' หากจำเป็นต้องใช้ โปรดขออนุมัติจากหัวหน้าก่อน",
        },
    },
    {
        "name": "Confidential (ทั่วไป) → เตือน",
        "enabled": True, "priority": 60,
        "rule": {
            "name": "warn-confidential",
            "min_label": Label.CONFIDENTIAL.value, "categories_any": [],
            "channels": [], "departments": [], "min_risk": 0,
            "action": Action.WARN.value, "require_approval": False,
            "coaching": "เนื้อหานี้อาจเป็นข้อมูลลับขององค์กร โปรดพิจารณาก่อนส่งไปยัง AI สาธารณะ "
                        "หรือใช้ AI ภายในองค์กรแทน",
        },
    },
    {
        "name": "Internal → บันทึกเฝ้าดู (Monitor)",
        "enabled": True, "priority": 90,
        "rule": {
            "name": "monitor-internal",
            "min_label": Label.INTERNAL.value, "categories_any": [],
            "channels": [], "departments": [], "min_risk": 0,
            "action": Action.MONITOR.value, "require_approval": False,
            "coaching": "",
        },
    },
]
