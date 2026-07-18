"""
ชั้นที่ 1: Pattern / Regex detectors
ตรวจรูปแบบตายตัวที่พบบ่อยในข้อมูลลับองค์กรไทย/สากล
— ทำงานในเครื่อง เร็ว ไม่ต้องเรียก AI (ตามหลัก Privacy-by-Design)

แต่ละ detector คืน (span, matched_text) ให้ engine ไปสร้าง Detection ต่อ
พร้อม validator (checksum) เพื่อลด False Positive
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..schemas import Label


@dataclass
class PatternDef:
    type: str
    category: str          # pii | financial | secret | legal | code | business
    label: Label
    weight: int            # น้ำหนักความเสี่ยง 0-100
    regex: re.Pattern
    reason_th: str
    validator: Optional[Callable[[str], bool]] = None
    mask: Optional[Callable[[str], str]] = None


# ---- Validators (checksum) ---------------------------------------------
def validate_thai_id(raw: str) -> bool:
    """เลขบัตรประชาชนไทย 13 หลัก — ตรวจ checksum หลักที่ 13."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 13:
        return False
    if digits == digits[0] * 13:  # 0000000000000 ฯลฯ
        return False
    total = sum(int(digits[i]) * (13 - i) for i in range(12))
    check = (11 - (total % 11)) % 10
    return check == int(digits[12])


def validate_luhn(raw: str) -> bool:
    """บัตรเครดิต — Luhn algorithm."""
    digits = [int(c) for c in re.sub(r"\D", "", raw)]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ---- Maskers ------------------------------------------------------------
def mask_middle(s: str, keep_start: int = 2, keep_end: int = 2) -> str:
    core = re.sub(r"\s+", "", s)
    if len(core) <= keep_start + keep_end:
        return "•" * len(core)
    return core[:keep_start] + "•" * (len(core) - keep_start - keep_end) + core[-keep_end:]


def mask_email(s: str) -> str:
    m = re.match(r"([^@]+)@(.+)", s)
    if not m:
        return "•••"
    name, dom = m.groups()
    shown = name[0] if name else ""
    return f"{shown}{'•' * max(1, len(name) - 1)}@{dom}"


def mask_secret(s: str) -> str:
    s = s.strip()
    if len(s) <= 8:
        return "•" * len(s)
    return s[:4] + "•" * (len(s) - 8) + s[-4:]


# ---- Pattern catalogue --------------------------------------------------
# หมายเหตุ: ลำดับสำคัญ — pattern เฉพาะเจาะจงควรมาก่อน pattern กว้าง
PATTERNS: list[PatternDef] = [
    # ----- Secrets / Credentials (ความลับทางเทคนิค) -----
    PatternDef(
        "aws_access_key", "secret", Label.RESTRICTED, 85,
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "พบ AWS Access Key", mask=mask_secret,
    ),
    PatternDef(
        "google_api_key", "secret", Label.RESTRICTED, 80,
        re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
        "พบ Google API Key", mask=mask_secret,
    ),
    PatternDef(
        "openai_key", "secret", Label.RESTRICTED, 85,
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b"),
        "พบ OpenAI/LLM API Key", mask=mask_secret,
    ),
    PatternDef(
        "anthropic_key", "secret", Label.RESTRICTED, 85,
        re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
        "พบ Anthropic API Key", mask=mask_secret,
    ),
    PatternDef(
        "slack_token", "secret", Label.RESTRICTED, 80,
        re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
        "พบ Slack Token", mask=mask_secret,
    ),
    PatternDef(
        "github_token", "secret", Label.RESTRICTED, 85,
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        "พบ GitHub Token", mask=mask_secret,
    ),
    PatternDef(
        "jwt", "secret", Label.CONFIDENTIAL, 60,
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
        "พบ JWT / Access Token", mask=mask_secret,
    ),
    PatternDef(
        "private_key", "secret", Label.RESTRICTED, 90,
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
        "พบ Private Key (คีย์เข้ารหัสส่วนตัว)", mask=lambda s: "-----BEGIN PRIVATE KEY----- •••",
    ),
    PatternDef(
        "generic_secret_assign", "secret", Label.CONFIDENTIAL, 55,
        re.compile(
            r"""(?ix)\b(?:api[_-]?key|secret|password|passwd|pwd|token|
            client[_-]?secret|access[_-]?key)\b\s*[:=]\s*['"]?[A-Za-z0-9/\+_\-]{8,}""",
        ),
        "พบการกำหนดค่ารหัสลับ/รหัสผ่านในข้อความ", mask=lambda s: re.sub(r"([:=]\s*['\"]?).+", r"\1••••••", s),
    ),
    PatternDef(
        "db_connection", "secret", Label.RESTRICTED, 80,
        re.compile(r"\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://[^\s'\"]+:[^\s'\"]+@[^\s'\"]+"),
        "พบ Database connection string (มีรหัสผ่าน)", mask=lambda s: re.sub(r"://[^@]+@", "://••••@", s),
    ),

    # ----- PII (ข้อมูลส่วนบุคคล — PDPA) -----
    PatternDef(
        "thai_national_id", "pii", Label.CONFIDENTIAL, 70,
        re.compile(r"\b\d(?:[\s-]?\d){12}\b"),
        "พบเลขบัตรประชาชนไทย 13 หลัก (ผ่าน checksum)",
        validator=validate_thai_id, mask=lambda s: mask_middle(s, 1, 1),
    ),
    PatternDef(
        "credit_card", "financial", Label.CONFIDENTIAL, 75,
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        "พบหมายเลขบัตรเครดิต (ผ่าน Luhn check)",
        validator=validate_luhn, mask=lambda s: mask_middle(s, 4, 4),
    ),
    PatternDef(
        "thai_phone", "pii", Label.INTERNAL, 30,
        re.compile(r"\b0[689]\d(?:[\s-]?\d){7}\b"),
        "พบเบอร์โทรศัพท์มือถือไทย", mask=lambda s: mask_middle(s, 3, 2),
    ),
    PatternDef(
        "email", "pii", Label.INTERNAL, 25,
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "พบอีเมล", mask=mask_email,
    ),
    PatternDef(
        "thai_passport", "pii", Label.CONFIDENTIAL, 60,
        re.compile(r"\b[A-Z]{1,2}\d{7}\b"),
        "พบเลขหนังสือเดินทาง", mask=lambda s: mask_middle(s, 2, 1),
    ),
    PatternDef(
        "iban", "financial", Label.CONFIDENTIAL, 55,
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
        "พบเลขบัญชี IBAN", mask=lambda s: mask_middle(s, 4, 2),
    ),
    PatternDef(
        "thai_bank_account", "financial", Label.CONFIDENTIAL, 55,
        re.compile(r"\b\d{3}[- ]?\d[- ]?\d{5}[- ]?\d\b"),
        "พบรูปแบบเลขบัญชีธนาคาร", mask=lambda s: mask_middle(s, 3, 1),
    ),
]


# ----- คำ/วลีบ่งชี้บริบทลับ (ใช้เป็น "สัญญาณเสริม" ไม่ตัดสินเดี่ยว ๆ) -----
# ให้ engine ใช้เพิ่มน้ำหนักและช่วย AI จับบริบท (ธุรกิจ/กฎหมาย/การเงิน)
KEYWORD_SIGNALS: list[tuple[str, str, Label, int, re.Pattern]] = [
    ("financial_internal", "financial", Label.CONFIDENTIAL, 35,
     re.compile(r"(?i)(งบการเงิน|งบดุล|ยังไม่ประกาศ|ผลประกอบการ|รายได้สุทธิ|กำไรสุทธิ|"
                r"unreleased|earnings|balance sheet|revenue|EBITDA|financial statement)")),
    ("mna", "business", Label.RESTRICTED, 45,
     re.compile(r"(?i)(ควบรวมกิจการ|เข้าซื้อกิจการ|ดีลลับ|M&A|merger|acquisition|"
                r"due diligence|term sheet)")),
    ("legal_nda", "legal", Label.CONFIDENTIAL, 35,
     re.compile(r"(?i)(สัญญาลับ|ข้อตกลงรักษาความลับ|NDA|non-disclosure|confidential agreement|"
                r"privileged|attorney[- ]client)")),
    ("strategy", "business", Label.CONFIDENTIAL, 30,
     re.compile(r"(?i)(กลยุทธ์ลับ|แผนธุรกิจลับ|ความลับทางการค้า|trade secret|"
                r"business strategy|roadmap ลับ|go-to-market)")),
    ("salary_hr", "pii", Label.CONFIDENTIAL, 35,
     re.compile(r"(?i)(เงินเดือน|ฐานเงินเดือน|payroll|salary|ค่าจ้างพนักงาน|ข้อมูลเงินเดือน)")),
    ("classified_marker", "business", Label.RESTRICTED, 40,
     re.compile(r"(?i)(ลับที่สุด|ลับมาก|ห้ามเผยแพร่|confidential|restricted|internal only|"
                r"ห้ามออกนอกองค์กร|top secret|strictly confidential)")),
    ("customer_data", "pii", Label.CONFIDENTIAL, 30,
     re.compile(r"(?i)(ข้อมูลลูกค้า|รายชื่อลูกค้า|ฐานข้อมูลลูกค้า|customer (?:list|database|records)|PII)")),
]
