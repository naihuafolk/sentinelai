"""
file_scanner.py — Endpoint Agent: สแกน & จัดประเภทไฟล์ในเครื่อง (โมดูล M1 Data Discovery)

สแกนโฟลเดอร์/ไฟล์ในเครื่อง ระบุว่าไฟล์ไหน "ลับ" ระดับใด โดยใช้เครื่องยนต์เดียวกับเซิร์ฟเวอร์
(Regex + Fingerprint; เพิ่ม AI ด้วย --ai) — ทำงานในเครื่อง ไม่ต้องมีเซิร์ฟเวอร์

ใช้:
  python agent/file_scanner.py "C:\\path\\to\\folder"
  python agent/file_scanner.py .  --ai            # ใช้ AI (BytePlus) ด้วย
  python agent/file_scanner.py docs --register    # ลงทะเบียนไฟล์ลับเป็น fingerprint (ต้องมีเซิร์ฟเวอร์)
  python agent/file_scanner.py docs --json out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

from common import cfg, local_engine

TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".py", ".js", ".ts", ".tsx",
            ".jsx", ".java", ".go", ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs",
            ".sql", ".yaml", ".yml", ".ini", ".env", ".sh", ".ps1", ".html", ".xml",
            ".conf", ".cfg", ".properties", ".toml", ".rs", ".kt", ".swift"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
MAX_BYTES = 800_000
LABEL_ORDER = {"Public": 0, "Internal": 1, "Confidential": 2, "Restricted": 3}
LABEL_ICON = {"Public": "  ", "Internal": "🔵", "Confidential": "🟠", "Restricted": "🔴"}


def extract_text(path: Path) -> str | None:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            r = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in r.pages[:30])
        if ext in TEXT_EXT or ext == "":
            data = path.read_bytes()[:MAX_BYTES]
            if b"\x00" in data[:1024]:  # ไบนารี
                return None
            return data.decode("utf-8", errors="ignore")
    except Exception:
        return None
    return None  # office/binary อื่น ๆ ข้าม (docx/xlsx ต้องติดตั้งไลบรารีเสริม)


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


async def scan(root: Path, use_ai: bool):
    eng = local_engine()
    results = []
    scanned = 0
    for path in iter_files(root):
        text = extract_text(path)
        if not text or not text.strip():
            continue
        scanned += 1
        cls = await eng.classify(text, force_ai=(True if use_ai else False))
        if cls.risk_score > 0 or cls.label != "Public":
            results.append({
                "path": str(path),
                "label": cls.label.value if hasattr(cls.label, "value") else str(cls.label),
                "risk": cls.risk_score,
                "categories": cls.categories,
                "detections": sorted({d.type for d in cls.detections}),
                "reasons": cls.reasons[:3],
                "_text": text,  # ใช้ตอน --register เท่านั้น (ไม่เขียนลงรายงาน)
            })
    results.sort(key=lambda r: (LABEL_ORDER.get(r["label"], 0), r["risk"]), reverse=True)
    return results, scanned


def register_fingerprints(results):
    """ลงทะเบียนไฟล์ Confidential/Restricted เป็น fingerprint ที่ backend."""
    n = 0
    for r in results:
        if LABEL_ORDER.get(r["label"], 0) < LABEL_ORDER["Confidential"]:
            continue
        try:
            resp = httpx.post(f"{cfg.api}/fingerprints",
                              data={"name": Path(r["path"]).name, "label": r["label"], "text": r["_text"][:20000]},
                              timeout=15)
            if resp.status_code == 200:
                n += 1
                print(f"   ✓ ลงทะเบียน: {Path(r['path']).name}")
        except Exception as e:
            print(f"   ✗ {Path(r['path']).name}: {e}")
    return n


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="SentinelAI — สแกนไฟล์ลับในเครื่อง")
    ap.add_argument("path", help="โฟลเดอร์หรือไฟล์ที่จะสแกน")
    ap.add_argument("--ai", action="store_true", help="ใช้ AI (BytePlus) ประเมินด้วย")
    ap.add_argument("--register", action="store_true", help="ลงทะเบียนไฟล์ลับเป็น fingerprint")
    ap.add_argument("--json", metavar="FILE", help="เขียนรายงานเป็น JSON")
    ap.add_argument("--min-risk", type=int, default=0, help="แสดงเฉพาะไฟล์ที่ความเสี่ยง >= ค่านี้")
    args = ap.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print("ไม่พบพาธ:", root)
        return 1

    print("=" * 70)
    print(f"🛡️  SentinelAI File Scanner — สแกน: {root}")
    print(f"   โหมด: Regex + Fingerprint{' + AI (BytePlus)' if args.ai else ''}")
    print("=" * 70)

    results, scanned = asyncio.run(scan(root, args.ai))
    shown = [r for r in results if r["risk"] >= args.min_risk]

    if not shown:
        print(f"\n✅ สแกน {scanned} ไฟล์ — ไม่พบไฟล์ที่เข้าข่ายลับ")
    else:
        print(f"\n⚠️  พบ {len(shown)} ไฟล์เข้าข่ายลับ (จาก {scanned} ไฟล์):\n")
        print(f"   {'ระดับ':<14}{'เสี่ยง':>6}  ไฟล์")
        print("   " + "-" * 64)
        for r in shown:
            icon = LABEL_ICON.get(r["label"], "  ")
            name = r["path"]
            if len(name) > 46:
                name = "…" + name[-45:]
            print(f"   {icon} {r['label']:<11}{r['risk']:>5}  {name}")
            print(f"      └ {', '.join(r['detections'][:4]) or r['reasons'][0] if r['reasons'] else ''}")
        # สรุป
        by = {}
        for r in shown:
            by[r["label"]] = by.get(r["label"], 0) + 1
        print("\n   สรุป: " + " · ".join(f"{LABEL_ICON.get(k,'')} {k}={v}" for k, v in sorted(by.items(), key=lambda x: -LABEL_ORDER.get(x[0], 0))))

    if args.json:
        clean = [{k: v for k, v in r.items() if k != "_text"} for r in results]
        Path(args.json).write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📄 เขียนรายงาน: {args.json}")

    if args.register:
        print("\n🔖 ลงทะเบียนไฟล์ลับเป็น fingerprint...")
        n = register_fingerprints(results)
        print(f"   ลงทะเบียนแล้ว {n} ไฟล์ (ครั้งต่อไปถ้าใครคัดลอกเนื้อหานี้ไป AI จะถูกจับ)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
