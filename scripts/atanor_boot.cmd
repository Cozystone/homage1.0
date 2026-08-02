@echo off
REM Bring ATANOR back after a reboot. One command, in the order that matters.
REM
REM   scripts\atanor_boot.cmd
REM
REM WHAT THIS STARTS, and why in this order:
REM   1. the API backend on :8502  -- the answer path; the life daemon has no hard dependency on it,
REM                                   but anything that talks to ATANOR does.
REM   2. the life daemon           -- one continuous process, its own metabolism sets the pulse.
REM                                   It resumes on the SAME persistent timeline, so continuity is
REM                                   kept across the reboot; only the moment is interrupted.
REM
REM WHAT THIS DOES NOT START: the hourly self-repair scheduled task. It was deleted deliberately on
REM 2026-08-01 -- repair is now something the mind does as one of its own capabilities
REM (Life._repair_turn), not something an outside clock permits. Do not put it back.
REM
REM SearXNG on :8888 is a separate service and is not managed here.
REM
REM To check afterwards:
REM   curl http://127.0.0.1:8502/health
REM   tail data\temporal_reasoning\life_daemon.log

cd /d "%~dp0.."

echo [boot] starting the API backend on :8502
start "" /b C:\ProgramData\miniconda3\python.exe -m uvicorn app.main:app --app-dir apps/api --port 8502 --host 127.0.0.1

echo [boot] waiting for the backend to come up
timeout /t 12 /nobreak >nul

echo [boot] starting the life daemon
start "" C:\ProgramData\miniconda3\pythonw.exe scripts\atanor_life.py

echo [boot] done. life stream -^> data\temporal_reasoning\life_daemon.log
