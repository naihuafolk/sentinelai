@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title SentinelAI Agent - Setup

echo ==================================================
echo    SentinelAI - Endpoint Agent (ป้องกันข้อมูลรั่ว)
echo ==================================================
echo.

REM --- 1) ตรวจ Python ---
python --version >nul 2>nul
if errorlevel 1 (
  echo [X] ไม่พบ Python ในเครื่องนี้
  echo.
  echo     กรุณาติดตั้ง Python ก่อน แล้วดับเบิลคลิกไฟล์นี้อีกครั้ง
  echo     ** ตอนติดตั้ง Python ให้ติ๊กช่อง "Add Python to PATH" ด้วย **
  echo.
  echo     กำลังเปิดหน้าดาวน์โหลด Python...
  start "" "https://www.python.org/downloads/"
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('python --version') do echo [1/4] พบ %%v
echo.

REM --- 2) ไลบรารีที่ต้องใช้ ---
echo [2/4] กำลังเตรียมไลบรารี (httpx)...
python -m pip install --quiet --disable-pip-version-check --upgrade httpx
if errorlevel 1 (
  echo [X] เตรียมไลบรารีไม่สำเร็จ - เช็คอินเทอร์เน็ตแล้วลองใหม่
  pause
  exit /b 1
)
echo     เรียบร้อย
echo.

REM --- 3) ใส่ Org Key ---
echo [3/4] ใส่คีย์เชื่อมองค์กร (คัดลอกจากเว็บ Dashboard: แท็บ "ตั้งค่า")
echo.
set "ORGKEY="
set /p "ORGKEY=    วาง Org Key แล้วกด Enter: "
if "%ORGKEY%"=="" (
  echo [X] ยังไม่ได้ใส่ Org Key - ยกเลิกการติดตั้ง
  pause
  exit /b 1
)
set /p "USR=    อีเมล/ชื่อผู้ใช้ (เว้นว่างได้ กด Enter ข้าม): "
set /p "DEPT=    แผนก (เว้นว่างได้ กด Enter ข้าม): "

(
  echo SENTINEL_BACKEND_URL=https://sentinelai.help
  echo SENTINEL_ORG_KEY=%ORGKEY%
  echo SENTINEL_USER=%USR%
  echo SENTINEL_DEPARTMENT=%DEPT%
) > "%~dp0sentinel.env"
echo     บันทึกการตั้งค่าแล้ว
echo.

REM --- 4) เปิดอัตโนมัติเมื่อเข้าเครื่อง + เริ่มทำงาน ---
echo [4/4] ตั้งให้เปิดเองทุกครั้งที่เปิดเครื่อง...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
(
  echo @echo off
  echo cd /d "%~dp0"
  echo start "" pythonw "%~dp0clipboard_guard.py"
) > "%STARTUP%\SentinelAI-Agent.bat"
echo     เรียบร้อย
echo.

echo กำลังเริ่มการป้องกัน...
start "" pythonw "%~dp0clipboard_guard.py"

echo.
echo ==================================================
echo    ✓ ติดตั้งสำเร็จ! SentinelAI กำลังเฝ้าคลิปบอร์ด
echo      - เปิดเองอัตโนมัติทุกครั้งที่เปิดเครื่อง
echo      - ลองคัดลอกเลขบัตรเครดิต/บัตรประชาชน เพื่อทดสอบ
echo ==================================================
echo.
pause
