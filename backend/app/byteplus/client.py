"""
ByteplusClient — ตัวเชื่อม BytePlus ModelArk (OpenAI-compatible)

ครอบคลุมโมเดลที่ SentinelAI ใช้จริงตามเอกสารคอนเซ็ปต์:
  - reasoning  (Dola/Seed reasoning) : สมองของ Policy Engine
  - vision / document understanding  : อ่านภาพหน้าจอ/สลิป/บัตร/PDF
  - embedding                        : Fingerprint เอกสารลับ + ค้นความคล้าย
  - translation (ผ่าน reasoning)     : ตรวจข้อมูลลับหลายภาษา

ออกแบบให้ "ปลอดภัยเสมอ": ถ้าไม่มี ARK_API_KEY หรือ API ล่ม จะคืนผลแบบ
graceful ให้ชั้น Regex/Fingerprint ทำงานต่อได้ (ระบบยังทำงาน 100%).

เอกสารอ้างอิง (BytePlus ModelArk):
  Base URL : https://ark.ap-southeast.bytepluses.com/api/v3
  Auth     : Authorization: Bearer $ARK_API_KEY
  Endpoint : POST /chat/completions        (OpenAI-compatible)
             POST /embeddings              (OpenAI-compatible)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from ..config import settings

log = logging.getLogger("sentinel.byteplus")


class ByteplusError(RuntimeError):
    pass


class ByteplusClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.ark_api_key).strip()
        self.base_url = (base_url or settings.ark_base_url).rstrip("/")
        self.timeout = timeout

    # ---- สถานะ ----------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ---- HTTP core ------------------------------------------------------
    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise ByteplusError("BytePlus API key not configured")
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            raise ByteplusError(f"ModelArk {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    # ---- Chat / Reasoning ----------------------------------------------
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_json: bool = False,
        extra: Optional[dict[str, Any]] = None,
    ) -> str:
        """เรียก chat completion แบบ OpenAI-compatible คืน content string."""
        payload: dict[str, Any] = {
            "model": model or settings.model_reasoning,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}
        if extra:
            payload.update(extra)
        data = await self._post("/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:  # pragma: no cover
            raise ByteplusError(f"unexpected chat response: {data}") from e

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        model: Optional[str] = None,
        images: Optional[list[str]] = None,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """เรียกโมเดลแล้ว parse ผลเป็น JSON (บังคับ response_format=json_object).

        รองรับภาพ (Vision/Document understanding) ผ่าน content array แบบ OpenAI.
        """
        user_content: Any = user
        if images:
            user_content = [{"type": "text", "text": user}]
            for img in images:
                user_content.append({"type": "image_url", "image_url": {"url": img}})
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        raw = await self.chat(
            messages,
            model=model or (settings.model_vision if images else settings.model_reasoning),
            response_json=True,
            max_tokens=max_tokens,
        )
        return _safe_json(raw)

    # ---- Embedding ------------------------------------------------------
    async def embed(
        self, texts: list[str], *, model: Optional[str] = None
    ) -> list[list[float]]:
        """คืน embedding vectors (OpenAI-compatible /embeddings)."""
        payload = {"model": model or settings.model_embedding, "input": texts}
        data = await self._post("/embeddings", payload)
        try:
            items = sorted(data["data"], key=lambda d: d.get("index", 0))
            return [it["embedding"] for it in items]
        except (KeyError, TypeError) as e:  # pragma: no cover
            raise ByteplusError(f"unexpected embedding response: {data}") from e

    # ---- Health probe ---------------------------------------------------
    async def ping(self) -> bool:
        """ทดสอบว่าเรียก ModelArk ได้จริงไหม (ใช้ในหน้า health)."""
        if not self.enabled:
            return False
        try:
            await self.chat(
                [{"role": "user", "content": "ping"}],
                model=settings.model_fast,
                max_tokens=1,
            )
            return True
        except Exception as e:  # pragma: no cover
            log.warning("BytePlus ping failed: %s", e)
            return False


def _safe_json(raw: str) -> dict[str, Any]:
    """ดึง JSON จากข้อความ (กันกรณีโมเดลใส่ ```json ... ``` หรือข้อความนำหน้า)."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {}


_client: Optional[ByteplusClient] = None


def get_client() -> ByteplusClient:
    global _client
    if _client is None:
        _client = ByteplusClient()
    return _client
