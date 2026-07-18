"""
SentinelAI API (FastAPI) — Multi-tenant SaaS
  - /auth/*          : สมัคร/ล็อกอิน (ผู้ใช้เข้ามาใช้เองได้)
  - /inspect, /inspect-response : ใช้ API key ขององค์กร (Extension/Agent)
  - endpoints อื่น ๆ : ต้องล็อกอิน (Bearer token) และผูกกับ org ของผู้ใช้
รัน:  uvicorn app.main:app --reload   (จากโฟลเดอร์ backend/)
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path as _Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, audit, auth, db, service
from .byteplus import get_client
from .classifier.fingerprint import get_index
from .config import settings
from .policy.db_bridge import invalidate as invalidate_policies
from .schemas import (
    AuthResponse, ClassifyOnlyResponse, DeviceOut, EventPage, FingerprintOut, Health,
    InspectRequest, InspectResponse, Label, LicenseUpdate, LoginRequest, OrgAdminOut, OrgOut,
    Policy, PolicyCreate, ResponseScanRequest, ResponseScanResult, SignupRequest,
    SimulateRequest, Stats, UserOut,
)
from .seed import ensure_defaults, register_sample_fingerprints, seed_demo, seed_org_defaults

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sentinel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    ensure_defaults()
    log.info("SentinelAI %s พร้อม | AI(BytePlus)=%s | orgs=%d",
             __version__, "เปิด" if settings.ai_enabled else "ปิด", db.count_orgs())
    yield


app = FastAPI(title="SentinelAI — AI Data Loss Prevention (SaaS)",
              description="ป้องกันข้อมูลลับองค์กรรั่วสู่ AI • Multi-tenant • BytePlus ModelArk",
              version=__version__, lifespan=lifespan)

_origins = ["*"] if settings.cors_origins.strip() == "*" else [
    o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)

API = "/api/v1"


def _org_out(org: dict) -> OrgOut:
    return OrgOut(id=org["id"], name=org["name"], api_key=org["api_key"],
                  plan=org.get("plan", "starter"), seats=org.get("seats", 5),
                  status=org.get("status", "trial"), quota_month=org.get("quota_month", 2000),
                  valid_until=org.get("valid_until"))


def _user_out(u: dict) -> UserOut:
    return UserOut(id=u["id"], email=u["email"], name=u.get("name") or "",
                   role=u.get("role", "admin"), is_platform_admin=auth.is_platform_admin(u))


# ============================ Auth ============================
@app.post(f"{API}/auth/signup", response_model=AuthResponse, tags=["auth"])
async def signup(req: SignupRequest):
    """สมัครใช้งาน — สร้างองค์กรใหม่ + ผู้ดูแล + คืน token และ API key ขององค์กร."""
    if db.get_user_by_email(req.email):
        raise HTTPException(409, "อีเมลนี้ถูกใช้สมัครแล้ว")
    api_key = auth.new_org_api_key()
    valid_until = (datetime.now(timezone.utc) + timedelta(days=settings.trial_days)).isoformat(timespec="seconds")
    org_id = db.create_org(req.org_name.strip(), api_key, plan="starter",
                           status="trial", seats=5, quota_month=2000, valid_until=valid_until)
    seed_org_defaults(org_id)  # ใส่ policy เริ่มต้นให้องค์กรใหม่
    uid = db.create_user(org_id, req.email, auth.hash_password(req.password), req.name)
    token = auth.make_token(uid, org_id, req.email.lower().strip())
    return AuthResponse(token=token, user=_user_out(db.get_user(uid)), org=_org_out(db.get_org(org_id)))


@app.post(f"{API}/auth/login", response_model=AuthResponse, tags=["auth"])
async def login(req: LoginRequest):
    user = db.get_user_by_email(req.email)
    if not user or not auth.verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    org = db.get_org(user["org_id"])
    token = auth.make_token(user["id"], org["id"], user["email"])
    return AuthResponse(token=token, user=_user_out(user), org=_org_out(org))


@app.get(f"{API}/auth/me", tags=["auth"])
async def me(ctx: dict = Depends(auth.get_current_user)):
    return {"user": _user_out(ctx["user"]), "org": _org_out(ctx["org"])}


# ============================ Core (Extension/Agent via org API key) ====
@app.post(f"{API}/inspect", response_model=InspectResponse, tags=["core"])
async def inspect(req: InspectRequest, request: Request, org: dict = Depends(auth.get_org_from_key)):
    """หัวใจ: ตรวจเนื้อหาก่อนส่งไป AI แล้วตัดสิน (ต้องส่ง header X-Sentinel-Key ขององค์กร)."""
    # identity จริงของเครื่อง = ลายนิ้วมือฮาร์ดแวร์ (device_fp); ถ้าไม่มีค่อย fallback เป็นชื่อเครื่อง
    identity = (req.device_fp or req.device or "").strip()
    ip = auth.client_ip(request)
    # License enforcement: กันเอา key ไปรันเกินสิทธิ์/ไม่ได้ซื้อ (seat นับตาม identity จริง)
    auth.check_license(org, device_id=identity)
    kind = "endpoint" if req.channel in ("desktop", "file") else "browser"
    # ลงทะเบียนอุปกรณ์ + ติดตามไอพี → จับการแชร์คีย์ (1 เครื่อง = 1 สิทธิ์)
    share = db.register_device(org["id"], identity, name=req.device, user=req.user,
                               dept=req.department, kind=kind, ip=ip)
    auth.check_device_sharing(org, identity, req.device, share)
    return await service.inspect(req, org_id=org["id"])


@app.post(f"{API}/inspect-response", response_model=ResponseScanResult, tags=["core"])
async def inspect_response(req: ResponseScanRequest, org: dict = Depends(auth.get_org_from_key)):
    """สแกน 'คำตอบจาก AI' (ป้องกันขาเข้า: data leak / unsafe / injection / hallucination)."""
    from .response_scan import scan_response
    return await scan_response(req.response_text, req.prompt_text)


@app.post(f"{API}/classify", response_model=ClassifyOnlyResponse, tags=["core"])
async def classify(req: SimulateRequest, ctx: dict = Depends(auth.get_current_user)):
    """จัดประเภทอย่างเดียว (Simulator) — ต้องล็อกอิน."""
    return await service.classify_only(req.text, use_ai=req.use_ai, org_id=ctx["org"]["id"])


# ============================ Events / Audit (login) ==================
@app.get(f"{API}/events", response_model=EventPage, tags=["audit"])
async def list_events(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                      decision: Optional[str] = None, channel: Optional[str] = None,
                      department: Optional[str] = None, label: Optional[str] = None,
                      search: Optional[str] = None, ctx: dict = Depends(auth.get_current_user)):
    items, total = db.query_events(ctx["org"]["id"], page=page, page_size=page_size,
                                   decision=decision, channel=channel, department=department,
                                   label=label, search=search)
    return EventPage(items=items, total=total, page=page, page_size=page_size)


@app.get(f"{API}/events.csv", tags=["audit"])
async def export_events_csv(ctx: dict = Depends(auth.get_current_user)):
    items, _ = db.query_events(ctx["org"]["id"], page=1, page_size=100000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "user", "department", "device", "channel", "action_type",
                "label", "risk_score", "categories", "decision", "policy", "ai_used", "detections", "reasons"])
    for e in items:
        w.writerow([e["ts"], e["user"], e["department"], e["device"], e["channel"], e["action_type"],
                    e["label"], e["risk_score"], "|".join(e["categories"]), e["decision"], e["policy_name"],
                    e["ai_used"], "|".join(e["detection_types"]), " ; ".join(e["reasons"])])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=sentinelai_audit.csv"})


@app.get(f"{API}/stats", response_model=Stats, tags=["audit"])
async def stats(ctx: dict = Depends(auth.get_current_user)):
    return audit.compute_stats(ctx["org"]["id"])


# ============================ Policies (login) ========================
@app.get(f"{API}/policies", response_model=list[Policy], tags=["policy"])
async def get_policies(ctx: dict = Depends(auth.get_current_user)):
    return db.get_policies(ctx["org"]["id"])


@app.post(f"{API}/policies", response_model=Policy, tags=["policy"])
async def create_policy(p: PolicyCreate, ctx: dict = Depends(auth.get_current_user)):
    org_id = ctx["org"]["id"]
    pid = db.insert_policy(org_id, p.name, p.enabled, p.priority, p.rule.model_dump())
    invalidate_policies(org_id)
    return {"id": pid, "name": p.name, "enabled": p.enabled, "priority": p.priority, "rule": p.rule.model_dump()}


@app.put(f"{API}/policies/{{pid}}", response_model=Policy, tags=["policy"])
async def edit_policy(pid: int, p: PolicyCreate, ctx: dict = Depends(auth.get_current_user)):
    org_id = ctx["org"]["id"]
    if not db.update_policy(org_id, pid, p.name, p.enabled, p.priority, p.rule.model_dump()):
        raise HTTPException(404, "ไม่พบนโยบาย")
    invalidate_policies(org_id)
    return {"id": pid, "name": p.name, "enabled": p.enabled, "priority": p.priority, "rule": p.rule.model_dump()}


@app.delete(f"{API}/policies/{{pid}}", tags=["policy"])
async def remove_policy(pid: int, ctx: dict = Depends(auth.get_current_user)):
    org_id = ctx["org"]["id"]
    if not db.delete_policy(org_id, pid):
        raise HTTPException(404, "ไม่พบนโยบาย")
    invalidate_policies(org_id)
    return {"deleted": pid}


# ============================ Fingerprints (login) ====================
@app.get(f"{API}/fingerprints", response_model=list[FingerprintOut], tags=["fingerprint"])
async def list_fingerprints(ctx: dict = Depends(auth.get_current_user)):
    return db.get_fingerprints(ctx["org"]["id"])


@app.post(f"{API}/fingerprints", response_model=FingerprintOut, tags=["fingerprint"])
async def add_fingerprint(name: str = Form(...), label: str = Form("Confidential"),
                          text: str = Form(""), file: Optional[UploadFile] = File(None),
                          ctx: dict = Depends(auth.get_current_user)):
    org_id = ctx["org"]["id"]
    content = text or ""
    if file is not None:
        raw = await file.read()
        content += "\n" + raw.decode("utf-8", errors="ignore")
    content = content.strip()
    if len(content) < 20:
        raise HTTPException(400, "เนื้อหาสั้นเกินไปสำหรับทำ fingerprint (อย่างน้อย 20 ตัวอักษร)")
    try:
        lab = Label(label)
    except ValueError:
        lab = Label.CONFIDENTIAL
    idx = get_index()
    hashes = sorted(idx.compute_hashes(content))
    fid, ts = db.insert_fingerprint(org_id, name, lab.value, len(hashes), hashes)
    idx.add_hashes(fid, name, lab, set(hashes), org_id=org_id)
    return FingerprintOut(id=fid, name=name, label=lab, chunks=len(hashes), created_at=ts)


@app.delete(f"{API}/fingerprints/{{fid}}", tags=["fingerprint"])
async def remove_fingerprint(fid: int, ctx: dict = Depends(auth.get_current_user)):
    org_id = ctx["org"]["id"]
    if not db.delete_fingerprint(org_id, fid):
        raise HTTPException(404, "ไม่พบ fingerprint")
    get_index().remove(fid, org_id=org_id)
    return {"deleted": fid}


# ============================ System ==================================
@app.get(f"{API}/config", tags=["system"])
async def public_config():
    return {"version": __version__,
            "monitored_channels": ["chatgpt", "gemini", "claude", "copilot", "deepseek", "grok", "perplexity"],
            **settings.public_dict()}


@app.get(f"{API}/health", response_model=Health, tags=["system"])
async def health(check_ai: bool = False):
    reachable = await get_client().ping() if (check_ai and settings.ai_enabled) else None
    return Health(version=__version__, ai_enabled=settings.ai_enabled, ark_reachable=reachable,
                  models={"reasoning": settings.model_reasoning, "fast": settings.model_fast,
                          "vision": settings.model_vision, "embedding": settings.model_embedding},
                  default_mode=settings.default_mode, total_events=db.count_events())


@app.post(f"{API}/admin/seed-demo", tags=["system"])
async def admin_seed_demo(ctx: dict = Depends(auth.get_current_user)):
    org_id = ctx["org"]["id"]
    if not db.get_fingerprints(org_id):
        register_sample_fingerprints(org_id)
    n = seed_demo(org_id)
    return {"seeded_events": n, "fingerprints": len(db.get_fingerprints(org_id))}


# ============================ Devices (org, login) ===================
@app.get(f"{API}/devices", response_model=list[DeviceOut], tags=["audit"])
async def list_org_devices(ctx: dict = Depends(auth.get_current_user)):
    """อุปกรณ์ที่ติดตั้งในองค์กร (เบราว์เซอร์/คอม) — เห็นว่าเครื่องไหนติดตั้งแล้ว."""
    return db.list_devices(ctx["org"]["id"])


# ============================ Super Admin (platform owner) ============
@app.get(f"{API}/admin/orgs", response_model=list[OrgAdminOut], tags=["admin"])
async def admin_list_orgs(ctx: dict = Depends(auth.get_platform_admin)):
    """รายชื่อองค์กรทั้งหมด + สถิติ (เฉพาะ Super Admin)."""
    return db.list_all_orgs()


@app.put(f"{API}/admin/orgs/{{oid}}", tags=["admin"])
async def admin_update_org(oid: int, lic: LicenseUpdate, ctx: dict = Depends(auth.get_platform_admin)):
    """แก้ไข license/แพ็กเกจ/สถานะขององค์กร (ระงับ/ต่ออายุ/ปรับ seat/quota)."""
    if not db.get_org(oid):
        raise HTTPException(404, "ไม่พบองค์กร")
    db.update_org_license(oid, plan=lic.plan, seats=lic.seats, status=lic.status,
                          quota_month=lic.quota_month, valid_until=lic.valid_until, name=lic.name)
    return {"ok": True, "org": db.get_org(oid)}


@app.get(f"{API}/admin/security-feed", tags=["admin"])
async def admin_security_feed(min_risk: int = 60, limit: int = 100,
                              ctx: dict = Depends(auth.get_platform_admin)):
    """ฟีดแจ้งเตือนความปลอดภัยข้ามทุกองค์กร (เหตุการณ์เสี่ยงสูง)."""
    events = db.all_events(limit=limit, min_risk=min_risk)
    org_names = {o["id"]: o["name"] for o in db.list_all_orgs()}
    for e in events:
        e["org_name"] = org_names.get(e.get("org_id"), "-")
    return {"items": events, "count": len(events)}


@app.get(f"{API}/admin/overview", tags=["admin"])
async def admin_overview(ctx: dict = Depends(auth.get_platform_admin)):
    """ภาพรวมทั้งแพลตฟอร์มสำหรับ Super Admin."""
    orgs = db.list_all_orgs()
    return {
        "total_orgs": len(orgs),
        "active": sum(1 for o in orgs if o.get("status") == "active"),
        "trial": sum(1 for o in orgs if o.get("status") == "trial"),
        "suspended": sum(1 for o in orgs if o.get("status") == "suspended"),
        "total_events": sum(o.get("events", 0) for o in orgs),
        "total_blocks": sum(o.get("blocks", 0) for o in orgs),
        "total_devices": sum(o.get("devices", 0) for o in orgs),
        "orgs": orgs,
    }


# ============================ Downloads (extension/agent) =============
def _zip_dir(folder: _Path, arc_root: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith((".db", ".pyc")):
                z.write(p, f"{arc_root}/{p.relative_to(folder).as_posix()}")
    buf.seek(0)
    return buf.read()


@app.get(f"{API}/download/{{what}}.zip", tags=["system"])
async def download_package(what: str):
    """ดาวน์โหลดตัวติดตั้ง: extension (เบราว์เซอร์) หรือ agent (คอม)."""
    root = settings.base_dir.parent
    mapping = {"extension": root / "extension", "agent": root / "agent"}
    folder = mapping.get(what)
    if not folder or not folder.exists():
        raise HTTPException(404, "ไม่พบแพ็กเกจ")
    data = _zip_dir(folder, f"sentinelai-{what}")
    return StreamingResponse(iter([data]), media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename=sentinelai-{what}.zip"})


# ============================ Dashboard (static) ======================
_dashboard_dir = settings.base_dir.parent / "dashboard"
if _dashboard_dir.exists():
    app.mount("/", StaticFiles(directory=str(_dashboard_dir), html=True), name="dashboard")
else:  # pragma: no cover
    @app.get("/")
    async def _root():
        return {"service": "SentinelAI", "version": __version__, "docs": "/docs"}
