# SentinelAI — production image
FROM python:3.12-slim

# ระบบพื้นฐาน (สำหรับ healthcheck curl)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ติดตั้ง dependency ก่อน (cache layer)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt gunicorn

# คัดลอกซอร์ส (backend + ส่วนที่เสิร์ฟ/ดาวน์โหลด)
COPY backend  /app/backend
COPY dashboard /app/dashboard
COPY extension /app/extension
COPY agent     /app/agent

WORKDIR /app/backend

# เก็บ DB บนโวลุ่มถาวร (ตั้งค่าใน .env / compose)
ENV SENTINEL_HOST=0.0.0.0 \
    SENTINEL_PORT=8000 \
    SENTINEL_DB_PATH=/data/sentinel.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

# 1 worker = ปลอดภัยกับ SQLite. เมื่อย้ายเป็น Postgres ค่อยเพิ่ม --workers
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
