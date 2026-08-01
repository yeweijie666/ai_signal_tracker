@echo off
REM 注册「每日定时爬取」Windows 计划任务（双击运行一次即可）
set "PY=C:\Users\27066\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
set "DIR=C:\Users\27066\WorkBuddy\Claw\ai_signal_tracker"
set "TASK=AI_Signal_Tracker_Daily"

schtasks /Create /TN "%TASK%" /TR "\"%PY%\" \"%DIR%\run.py\"" /SC DAILY /ST 08:00 /F
if %errorlevel%==0 (
  echo.
  echo [OK] 已创建每日 08:00 自动运行的计划任务：%TASK%
  echo      爬取结果写入 %DIR%\signals.json，打开 dashboard.html 即可看时间线。
) else (
  echo [失败] 请以管理员身份运行本文件，或手动执行 README 中的 schtasks 命令。
)
pause
