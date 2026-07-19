@echo off
chcp 65001 >nul
title SentinelAI Agent - ถอนการติดตั้ง

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP%\SentinelAI-Agent.bat" del "%STARTUP%\SentinelAI-Agent.bat"

echo ยกเลิกการเปิดอัตโนมัติแล้ว
echo (โปรแกรมที่กำลังทำงานอยู่จะหยุดเองเมื่อรีสตาร์ท/ปิดเครื่อง)
echo ถ้าต้องการลบทั้งหมด: ลบโฟลเดอร์นี้ได้เลย
echo.
pause
