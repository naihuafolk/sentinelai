"""
API contract ของ SentinelAI (Pydantic v2).
เป็น "สัญญา" ที่ Browser Extension, Endpoint Agent และ Dashboard ใช้ร่วมกัน.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---- Enums --------------------------------------------------------------
class Label(str, Enum):
    PUBLIC = "Public"
    INTERNAL = "Internal"
    CONFIDENTIAL = "Confidential"
    RESTRICTED = "Restricted"


class Action(str, Enum):
    ALLOW = "allow"      # ปล่อยผ่าน (Monitor คือ allow + บันทึก)
    MONITOR = "monitor"  # บันทึกอย่างเดียว ไม่ขวาง
    WARN = "warn"        # เตือน แต่ยืนยันแล้วส่งได้
    REDACT = "redact"    # ปิดบังส่วนลับแล้วให้ส่งที่เหลือ
    BLOCK = "block"      # ห้ามส่งเด็ดขาด


Channel = Literal[
    "chatgpt", "gemini", "claude", "copilot", "deepseek", "grok",
    "perplexity", "desktop", "file", "other",
]
ActionType = Literal["paste", "type", "submit", "upload", "attach", "copy", "scan", "screenshot"]


# ---- Detections & Classification ---------------------------------------
class Detection(BaseModel):
    type: str = Field(..., description="ชนิดที่ตรวจพบ เช่น thai_national_id, api_key")
    category: str = Field(..., description="หมวด: pii, financial, secret, legal, code, business")
    label: Label = Field(..., description="ระดับความลับที่ชนิดนี้บ่งชี้")
    value_masked: str = Field(..., description="ค่าที่พบแบบปิดบัง (ไม่เก็บค่าจริง)")
    span: tuple[int, int] = Field(..., description="ตำแหน่ง [start, end] ในข้อความ")
    weight: int = Field(..., description="น้ำหนักความเสี่ยงที่ชนิดนี้เพิ่ม (0-100)")
    engine: Literal["regex", "fingerprint", "ai"] = "regex"


class Classification(BaseModel):
    label: Label = Label.PUBLIC
    risk_score: int = Field(0, ge=0, le=100)
    categories: list[str] = Field(default_factory=list)
    detections: list[Detection] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list, description="เหตุผลอ่านง่ายสำหรับพนักงาน/แอดมิน")
    engine: str = "regex"
    ai_used: bool = False
    ai_summary: Optional[str] = None


# ---- Inspect (หัวใจของ Interception Flow) -------------------------------
class InspectRequest(BaseModel):
    text: str = Field("", description="เนื้อหาที่กำลังจะส่งไปยัง AI")
    channel: Channel = "other"
    destination_url: str = ""
    action_type: ActionType = "paste"
    user: str = Field("unknown", description="อีเมล/ชื่อผู้ใช้จาก extension/agent")
    department: str = Field("", description="แผนก (ถ้ามี) เพื่อ match policy")
    device: str = Field("", description="ชื่อเครื่อง/asset id (สำหรับแสดงผล)")
    device_fp: str = Field("", description="ลายนิ้วมือฮาร์ดแวร์/เบราว์เซอร์ = identity จริงของเครื่อง (กันเอาคีย์ไปแชร์หลายเครื่อง)")
    images: list[str] = Field(default_factory=list, description="data URI ของภาพที่จะแนบ (สำหรับ Vision)")
    context: str = Field("", description="บริบทก่อนหน้า (optional)")
    dry_run: bool = Field(False, description="ทดสอบโดยไม่บันทึก Audit Log")


class PolicyMatch(BaseModel):
    policy_id: Optional[int] = None
    policy_name: str = "default"
    matched_rule: str = ""


class InspectResponse(BaseModel):
    decision: Action
    classification: Classification
    redacted_text: Optional[str] = None
    safe_rewrite: Optional[str] = None      # AI เขียนคำถามใหม่ให้ปลอดภัย (คงเจตนาเดิม)
    safe_rewrite_note: Optional[str] = None
    policy: PolicyMatch
    coaching: Optional[str] = None
    event_id: Optional[str] = None
    latency_ms: int = 0


# ---- Policies -----------------------------------------------------------
class PolicyRule(BaseModel):
    """เงื่อนไข -> การกระทำ (Policy Builder)."""
    name: str = ""
    # เงื่อนไข (ค่าว่าง/None = ไม่สนใจเงื่อนไขนั้น)
    min_label: Optional[Label] = None          # >= ระดับนี้
    categories_any: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)    # ว่าง = ทุกช่องทาง
    departments: list[str] = Field(default_factory=list)  # ว่าง = ทุกแผนก
    min_risk: int = 0
    # ผลลัพธ์
    action: Action = Action.WARN
    require_approval: bool = False
    coaching: str = ""


class Policy(BaseModel):
    id: Optional[int] = None
    name: str
    enabled: bool = True
    priority: int = 100  # เลขน้อย = สำคัญกว่า (ตรวจก่อน)
    rule: PolicyRule


class PolicyCreate(BaseModel):
    name: str
    enabled: bool = True
    priority: int = 100
    rule: PolicyRule


# ---- Events / Audit -----------------------------------------------------
class Event(BaseModel):
    id: str
    ts: str
    user: str
    department: str
    device: str
    channel: str
    destination_url: str
    action_type: str
    label: Label
    risk_score: int
    categories: list[str]
    decision: Action
    reasons: list[str]
    policy_name: str
    ai_used: bool
    detection_types: list[str]
    content_excerpt: Optional[str] = None  # เก็บเฉพาะเมื่อ STORE_CONTENT=true


class EventPage(BaseModel):
    items: list[Event]
    total: int
    page: int
    page_size: int


# ---- Stats (Dashboard) --------------------------------------------------
class TrendPoint(BaseModel):
    date: str
    detections: int
    blocks: int


class Stats(BaseModel):
    detections_30d: int
    blocks_30d: int
    redactions_30d: int
    warns_30d: int
    top_department: str
    active_agents_pct: int
    by_channel: dict[str, int]
    by_category: dict[str, int]
    by_department: dict[str, int]
    by_label: dict[str, int]
    trend: list[TrendPoint]


# ---- Fingerprints -------------------------------------------------------
class FingerprintOut(BaseModel):
    id: int
    name: str
    label: Label
    chunks: int
    created_at: str


# ---- Auth / Multi-tenant ------------------------------------------------
class SignupRequest(BaseModel):
    org_name: str = Field(..., min_length=2, description="ชื่อองค์กร/บริษัท")
    email: str = Field(..., description="อีเมลผู้ดูแล")
    password: str = Field(..., min_length=6)
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class OrgOut(BaseModel):
    id: int
    name: str
    api_key: str
    plan: str = "starter"
    seats: int = 5
    status: str = "trial"
    quota_month: int = 2000
    valid_until: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    name: str = ""
    role: str = "admin"
    is_platform_admin: bool = False


class AuthResponse(BaseModel):
    token: str
    user: UserOut
    org: OrgOut


class LicenseUpdate(BaseModel):
    plan: Optional[str] = None
    seats: Optional[int] = None
    status: Optional[Literal["trial", "active", "suspended"]] = None
    quota_month: Optional[int] = None
    valid_until: Optional[str] = None
    name: Optional[str] = None


class OrgAdminOut(BaseModel):
    id: int
    name: str
    plan: str
    status: str
    seats: int
    quota_month: int
    valid_until: Optional[str] = None
    created_at: Optional[str] = None
    users: int = 0
    devices: int = 0
    events: int = 0
    blocks: int = 0


class DeviceOut(BaseModel):
    id: int
    device_id: str
    user: str = ""
    department: str = ""
    kind: str = "browser"
    os: str = ""
    last_seen: Optional[str] = None
    events: int = 0


# ---- Health -------------------------------------------------------------
class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    ai_enabled: bool
    ark_reachable: Optional[bool] = None
    models: dict[str, str]
    default_mode: str
    total_events: int


# ---- Simulation (Policy testing / demo) --------------------------------
class SimulateRequest(BaseModel):
    text: str
    channel: Channel = "chatgpt"
    department: str = ""
    use_ai: Optional[bool] = None  # None = ตามค่าระบบ


class ClassifyOnlyResponse(BaseModel):
    classification: Classification
    redacted_text: str
    latency_ms: int


# ---- AI Response Scan (ป้องกันขาเข้า — สแกนสิ่งที่ AI ตอบกลับ) ----------
class ResponseScanRequest(BaseModel):
    response_text: str = Field(..., description="ข้อความที่ AI ตอบกลับมา")
    prompt_text: str = Field("", description="คำถามเดิม (ช่วยตรวจ injection/บริบท)")
    channel: Channel = "other"


class ResponseFinding(BaseModel):
    type: Literal["data_leak", "unsafe_content", "prompt_injection", "hallucination"]
    severity: Literal["low", "medium", "high"]
    detail: str


class ResponseScanResult(BaseModel):
    action: Literal["allow", "flag", "block"]
    risk_score: int = Field(0, ge=0, le=100)
    findings: list[ResponseFinding] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    ai_used: bool = False
    latency_ms: int = 0
