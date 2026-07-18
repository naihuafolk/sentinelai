"""
clipboard_guard.py — Endpoint Agent: เฝ้าคลิปบอร์ดระดับเครื่อง (โมดูล M2 นอกเบราว์เซอร์)

ป้องกันข้อมูลลับที่จะถูก "คัดลอก → วาง" ลงแอปใดก็ได้:
แอป AI เดสก์ท็อป (ChatGPT/Claude/Copilot), Slack, อีเมล, Word, LINE ฯลฯ

เมื่อพบข้อมูลลับในคลิปบอร์ด:
  block  -> ล้างคลิปบอร์ด (วางไม่ได้) + แจ้งเตือน
  redact -> แทนที่ด้วยฉบับปิดบัง + แจ้งเตือน
  warn   -> แจ้งเตือน ให้ผู้ใช้เลือก (ล้างทิ้ง / เก็บไว้)
ทุกเหตุการณ์ส่งเข้า backend เพื่อบันทึกใน Audit Log/Dashboard เดียวกับฝั่งเบราว์เซอร์

ใช้ tkinter (มากับ Python) — ไม่ต้องติดตั้งไลบรารีเพิ่ม
รัน:  python agent/clipboard_guard.py
ทดสอบไม่เปิด GUI:  python agent/clipboard_guard.py --selftest "ข้อความ"
"""
from __future__ import annotations

import sys
import json

from common import cfg, foreground_app, inspect_remote, backend_alive

POLL_MS = 700
MIN_LEN = 6
MAX_SEND = 8000

LABEL_TH = {"Public": "ทั่วไป", "Internal": "ภายในองค์กร", "Confidential": "ลับ", "Restricted": "ลับที่สุด"}
DEC_COLOR = {"block": "#ef4444", "redact": "#8b5cf6", "warn": "#f59e0b", "monitor": "#64748b"}
CLEARED_NOTICE = "[SentinelAI: ล้างข้อมูลลับออกจากคลิปบอร์ดแล้ว]"


def evaluate(text: str) -> dict | None:
    """ส่งข้อความให้ backend ประเมิน (offline fallback ถ้าเซิร์ฟเวอร์ล่ม)."""
    app_title, _ = foreground_app()
    res = inspect_remote(text[:MAX_SEND], channel="desktop", action_type="copy", destination=app_title)
    if res is not None:
        return res
    # offline: ใช้ pipeline เดียวกันในเครื่อง
    try:
        import asyncio
        from app.service import inspect as svc_inspect
        from app.schemas import InspectRequest
        from common import local_engine
        local_engine()  # เตรียม db/policy/fingerprint
        r = asyncio.run(svc_inspect(InspectRequest(
            text=text[:MAX_SEND], channel="desktop", action_type="copy",
            destination_url=app_title, user=cfg.user, department=cfg.department, device=cfg.device)))
        return json.loads(r.model_dump_json())
    except Exception as e:
        print("  [offline eval error]", e)
        return None


# ---------------------- โหมดทดสอบ (ไม่เปิด GUI) ----------------------
def selftest(text: str) -> int:
    print(f"เซิร์ฟเวอร์: {'ออนไลน์' if backend_alive() else 'ออฟไลน์ (ใช้เครื่องยนต์ในเครื่อง)'}")
    app_title, is_ai = foreground_app()
    print(f"แอปที่โฟกัส: {app_title} {'(เป็นแอป AI!)' if is_ai else ''}")
    res = evaluate(text)
    if not res:
        print("ประเมินไม่สำเร็จ")
        return 1
    c = res["classification"]
    print(f"\nการตัดสิน : {res['decision'].upper()}")
    print(f"ระดับ     : {c['label']}  |  ความเสี่ยง: {c['risk_score']}/100")
    print(f"เหตุผล    : {c['reasons'][:3]}")
    if res.get("redacted_text"):
        print(f"ฉบับปิดบัง: {res['redacted_text'][:120]}")
    if res.get("coaching"):
        print(f"คำแนะนำ   : {res['coaching']}")
    return 0


# ---------------------- โหมดจริง (GUI) ----------------------
def run_gui() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()  # ซ่อนหน้าต่างหลัก
    state = {"last": "", "self_set": ""}

    def set_clip(value: str):
        state["self_set"] = value
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update()

    def popup(res: dict):
        c = res["classification"]
        dec = res["decision"]
        color = DEC_COLOR.get(dec, "#f59e0b")
        app_title, _ = foreground_app()
        win = tk.Toplevel(root)
        win.title("SentinelAI")
        win.configure(bg="#0f172a")
        win.attributes("-topmost", True)
        w, h = 430, 300
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{sw-w-24}+{sh-h-64}")
        win.overrideredirect(False)

        tk.Frame(win, bg=color, height=5).pack(fill="x")
        body = tk.Frame(win, bg="#0f172a")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        icon = {"block": "⛔", "redact": "🛡️", "warn": "⚠️", "monitor": "👁️"}.get(dec, "🛡️")
        tk.Label(body, text="🛡️ SENTINELAI", bg="#0f172a", fg="#10b981",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        title = {"block": "บล็อก: ล้างข้อมูลลับจากคลิปบอร์ดแล้ว",
                 "redact": "ปิดบังข้อมูลลับในคลิปบอร์ดแล้ว",
                 "warn": "พบข้อมูลที่อาจเป็นความลับในคลิปบอร์ด",
                 "monitor": "บันทึกเหตุการณ์"}.get(dec, "แจ้งเตือน")
        tk.Label(body, text=f"{icon}  {title}", bg="#0f172a", fg="#f8fafc",
                 font=("Segoe UI", 12, "bold"), wraplength=w-56, justify="left").pack(anchor="w", pady=(4, 8))
        tk.Label(body, text=f"ระดับ: {LABEL_TH.get(c['label'], c['label'])} · ความเสี่ยง {c['risk_score']}/100"
                          f"\nปลายทาง: {app_title}",
                 bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 9), justify="left").pack(anchor="w")
        reason = (c["reasons"] or ["-"])[0]
        tk.Label(body, text=f"• {reason}", bg="#0b1220", fg="#cbd5e1", font=("Segoe UI", 9),
                 wraplength=w-56, justify="left").pack(anchor="w", fill="x", pady=8, ipady=6, ipadx=8)
        if res.get("coaching"):
            tk.Label(body, text=f"💡 {res['coaching']}", bg="#0f172a", fg="#a7f3d0",
                     font=("Segoe UI", 9), wraplength=w-56, justify="left").pack(anchor="w")

        btns = tk.Frame(body, bg="#0f172a")
        btns.pack(side="bottom", fill="x", pady=(10, 0))

        def close():
            win.destroy()

        def clear_and_close():
            set_clip(CLEARED_NOTICE)
            win.destroy()

        if dec == "warn":
            tk.Button(btns, text="ล้างทิ้ง (ปลอดภัย)", command=clear_and_close, bg="#ef4444", fg="white",
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=6).pack(side="left", expand=True, fill="x", padx=(0, 6))
            tk.Button(btns, text="เก็บไว้ ฉันยืนยัน", command=close, bg="#1e293b", fg="#cbd5e1",
                      relief="flat", font=("Segoe UI", 10), padx=12, pady=6).pack(side="left", expand=True, fill="x")
        else:
            tk.Button(btns, text="เข้าใจแล้ว", command=close, bg="#10b981", fg="#04160e",
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=6).pack(fill="x")
        win.after(15000, lambda: win.winfo_exists() and win.destroy())

    def handle(text: str):
        res = evaluate(text)
        if not res:
            return
        dec = res["decision"]
        if dec == "block":
            set_clip(CLEARED_NOTICE)
            popup(res)
        elif dec == "redact":
            set_clip(res.get("redacted_text") or CLEARED_NOTICE)
            popup(res)
        elif dec == "warn":
            popup(res)
        # monitor/allow: เงียบ (บันทึกที่ backend แล้ว)
        print(f"  [{dec}] {res['classification']['label']} risk={res['classification']['risk_score']}")

    def poll():
        try:
            txt = root.clipboard_get()
        except Exception:
            txt = ""
        if txt and len(txt) >= MIN_LEN and txt != state["last"] and txt != state["self_set"]:
            state["last"] = txt
            try:
                handle(txt)
            except Exception as e:
                print("  [handle error]", e)
        root.after(POLL_MS, poll)

    online = backend_alive()
    print("=" * 56)
    print("🛡️  SentinelAI Clipboard Guard — กำลังเฝ้าคลิปบอร์ด")
    print(f"   ผู้ใช้: {cfg.user} · เครื่อง: {cfg.device}")
    print(f"   เซิร์ฟเวอร์: {'ออนไลน์ ✓' if online else 'ออฟไลน์ (ใช้เครื่องยนต์ในเครื่อง)'}")
    print("   กด Ctrl+C เพื่อหยุด")
    print("=" * 56)
    root.after(POLL_MS, poll)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        text = sys.argv[2] if len(sys.argv) >= 3 else "API key sk-proj-abcd1234efgh5678ijkl9012mnop3456"
        return selftest(text)
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
