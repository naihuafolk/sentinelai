"""
การตั้งค่ากลางของ SentinelAI — อ่านจาก environment / ไฟล์ .env
ไม่พึ่ง pydantic-settings เพื่อลด dependency ให้รันได้ทันที
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """โหลด .env แบบง่าย (ไม่ override ค่าที่ตั้งใน env จริงอยู่แล้ว)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_BASE_DIR = Path(__file__).resolve().parent.parent
_load_dotenv(_BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class Settings:
    # BytePlus ModelArk
    ark_api_key: str = os.getenv("ARK_API_KEY", "").strip()
    ark_base_url: str = os.getenv(
        "ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3"
    ).rstrip("/")
    model_reasoning: str = os.getenv("ARK_MODEL_REASONING", "seed-2-0-pro-260328")
    model_fast: str = os.getenv("ARK_MODEL_FAST", "seed-2-0-lite-260428")
    model_vision: str = os.getenv("ARK_MODEL_VISION", "seed-2-0-pro-260328")
    model_embedding: str = os.getenv("ARK_MODEL_EMBEDDING", "skylark-embedding-vision-251215")

    # พฤติกรรม
    default_mode: str = os.getenv("SENTINEL_DEFAULT_MODE", "warn").lower()
    ai_risk_threshold: int = _int("SENTINEL_AI_RISK_THRESHOLD", 35)
    # จำนวนอุปกรณ์ทั้งหมดในองค์กร (สำหรับคำนวณ % ครอบคลุม Agent); 0 = ไม่ทราบ
    fleet_size: int = _int("SENTINEL_FLEET_SIZE", 0)
    # SaaS licensing
    admin_emails: str = os.getenv("SENTINEL_ADMIN_EMAILS", "")   # อีเมล Super Admin (คั่นด้วย ,)
    trial_days: int = _int("SENTINEL_TRIAL_DAYS", 14)
    # กันเอาไปรันมั่ว: บล็อกเมื่อ license ไม่ผ่าน (true) หรือแค่เตือน+ปล่อยผ่าน (false)
    enforce_license: bool = _bool("SENTINEL_ENFORCE_LICENSE", True)
    # กันแชร์คีย์ (1 เครื่อง = 1 สิทธิ์): ถ้า "ลายนิ้วมือเครื่อง" เดียวถูกใช้จากไอพีมากกว่านี้
    # ภายในหน้าต่างเวลา → ถือว่าแชร์คีย์ (แจ้งเตือน + บล็อกถ้า enforce_license)
    share_max_ips: int = _int("SENTINEL_SHARE_MAX_IPS", 3)      # >3 ไอพี (คือ 4+) = สงสัยแชร์
    share_window_min: int = _int("SENTINEL_SHARE_WINDOW_MIN", 20)  # หน้าต่างเวลา (นาที)

    # Stripe billing (ไม่ตั้งคีย์ = ปิดจ่ายเงินอัตโนมัติ ใช้ manual ผ่าน Super Admin ต่อได้)
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "").strip()
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    stripe_publishable_key: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
    stripe_price_starter: str = os.getenv("STRIPE_PRICE_STARTER", "").strip()   # price id (per-seat/เดือน)
    stripe_price_business: str = os.getenv("STRIPE_PRICE_BUSINESS", "").strip()
    public_base_url: str = os.getenv("SENTINEL_PUBLIC_URL", "https://sentinelai.help").rstrip("/")

    @property
    def billing_enabled(self) -> bool:
        return bool(self.stripe_secret_key)

    def admin_email_set(self) -> set:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}
    store_content: bool = _bool("SENTINEL_STORE_CONTENT", False)
    db_path: str = os.getenv("SENTINEL_DB_PATH", str(_BASE_DIR / "sentinel.db"))
    cors_origins: str = os.getenv("SENTINEL_CORS_ORIGINS", "*")

    # เซิร์ฟเวอร์
    host: str = os.getenv("SENTINEL_HOST", "127.0.0.1")
    port: int = _int("SENTINEL_PORT", 8000)

    base_dir: Path = _BASE_DIR

    @property
    def ai_enabled(self) -> bool:
        """เปิดใช้ AI Semantic เฉพาะเมื่อมีคีย์ BytePlus."""
        return bool(self.ark_api_key)

    def public_dict(self) -> dict:
        """ค่าที่ปลอดภัยจะเปิดเผย (ไม่รวม API key)."""
        return {
            "ai_enabled": self.ai_enabled,
            "ark_base_url": self.ark_base_url,
            "default_mode": self.default_mode,
            "ai_risk_threshold": self.ai_risk_threshold,
            "store_content": self.store_content,
            "billing_enabled": self.billing_enabled,
            "models": {
                "reasoning": self.model_reasoning,
                "fast": self.model_fast,
                "vision": self.model_vision,
                "embedding": self.model_embedding,
            },
        }


settings = Settings()
