"""
common.py — โครงร่วมของ Endpoint Agent (SentinelAI)
  - โหลดการตั้งค่า (backend URL, ตัวตนผู้ใช้) จาก .env / environment
  - เรียก backend /inspect (ให้เหตุการณ์ไหลเข้า Audit Log/Dashboard เดียวกัน)
  - โหลดเครื่องยนต์จัดประเภทภายในเครื่อง (offline fallback / ใช้กับ file scanner)
  - ตรวจชื่อแอปที่กำลังโฟกัส (Windows) เพื่อรู้ว่าจะเอาข้อมูลไปวางที่ไหน
"""
from __future__ import annotations

import hashlib
import os
import platform
import socket
import sys
import uuid
from pathlib import Path

import httpx

# ---- path: ให้ import โมดูล backend ได้ (เครื่องยนต์เดียวกับเซิร์ฟเวอร์) ----
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _load_env() -> None:
    """โหลด backend/.env แบบเบา ๆ (ไม่ override ค่าที่ตั้งไว้แล้ว)."""
    envp = _BACKEND / ".env"
    if not envp.exists():
        return
    for line in envp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_env()


# ---- ลายนิ้วมือฮาร์ดแวร์ (กันเอาคีย์ไปแชร์หลายเครื่อง: 1 เครื่อง = 1 สิทธิ์) ----
def _machine_guid() -> str:
    """รหัสเครื่องระดับ OS ที่คงที่ (Windows MachineGuid / Linux machine-id / macOS IOPlatformUUID)."""
    try:
        sysname = platform.system()
        if sysname == "Windows":
            import winreg  # type: ignore
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                return winreg.QueryValueEx(k, "MachineGuid")[0]
        if sysname == "Darwin":
            import subprocess
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True, timeout=5)
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        else:  # Linux/อื่น ๆ
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                fpath = Path(p)
                if fpath.exists():
                    return fpath.read_text().strip()
    except Exception:
        pass
    return ""


def hardware_fingerprint() -> str:
    """ลายนิ้วมือคงที่ต่อเครื่อง — คัดลอกโฟลเดอร์/คีย์ไปเครื่องอื่น = ลายนิ้วมือเปลี่ยน = ต้องใช้สิทธิ์ใหม่."""
    override = os.getenv("SENTINEL_DEVICE_FP", "").strip()
    if override:
        return override
    parts = [
        _machine_guid(),
        str(uuid.getnode()),   # node id อิง MAC
        platform.node(),       # hostname
        platform.machine(),    # สถาปัตยกรรม CPU
        platform.system(),
    ]
    raw = "|".join(p for p in parts if p) or socket.gethostname()
    return "hw_" + hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:32]


class AgentConfig:
    backend_url: str = os.getenv("SENTINEL_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    user: str = os.getenv("SENTINEL_USER", os.getenv("USERNAME", "unknown"))
    department: str = os.getenv("SENTINEL_DEPARTMENT", "")
    device: str = os.getenv("SENTINEL_DEVICE", socket.gethostname())
    device_fp: str = hardware_fingerprint()  # identity จริง (กันแชร์คีย์)
    org_key: str = os.getenv("SENTINEL_ORG_KEY", "")  # API key ขององค์กร (SaaS)

    @property
    def api(self) -> str:
        return self.backend_url + "/api/v1"


cfg = AgentConfig()


# ---- เรียก backend ---------------------------------------------------------
def inspect_remote(text: str, *, channel: str, action_type: str,
                   destination: str = "", images=None, dry_run: bool = False) -> dict | None:
    """ส่งให้ backend /inspect — คืน dict ผลลัพธ์ หรือ None ถ้าเชื่อมต่อไม่ได้."""
    payload = {
        "text": text, "channel": channel, "destination_url": destination,
        "action_type": action_type, "user": cfg.user, "department": cfg.department,
        "device": cfg.device, "device_fp": cfg.device_fp, "images": images or [], "dry_run": dry_run,
    }
    headers = {"X-Sentinel-Key": cfg.org_key} if cfg.org_key else {}
    try:
        r = httpx.post(f"{cfg.api}/inspect", json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def backend_alive() -> bool:
    try:
        return httpx.get(f"{cfg.api}/health", timeout=5).status_code == 200
    except Exception:
        return False


# ---- เครื่องยนต์ภายในเครื่อง (offline) ------------------------------------
_engine = None


def local_engine():
    """คืน ClassificationEngine ของ backend (ทำงานในเครื่อง ไม่ต้องมีเซิร์ฟเวอร์)."""
    global _engine
    if _engine is None:
        from app.classifier import get_engine
        from app.seed import ensure_defaults
        from app import db
        db.init_db()
        ensure_defaults()  # โหลด fingerprint + policy เริ่มต้น
        _engine = get_engine()
    return _engine


# ---- ตรวจแอปที่กำลังโฟกัส (Windows) ---------------------------------------
_AI_APPS = ("chatgpt", "claude", "copilot", "gemini", "deepseek", "grok", "perplexity", "openai")


def foreground_app() -> tuple[str, bool]:
    """คืน (ชื่อหน้าต่างที่โฟกัส, เป็นแอป AI ไหม). ใช้ได้บน Windows; อื่น ๆ คืน unknown."""
    try:
        import ctypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        ln = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(ln + 1)
        u.GetWindowTextW(h, buf, ln + 1)
        title = (buf.value or "").strip() or "unknown"
    except Exception:
        title = "unknown"
    is_ai = any(a in title.lower() for a in _AI_APPS)
    return title, is_ai
