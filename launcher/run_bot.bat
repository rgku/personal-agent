@echo off
title Personal Agent
cd /d "%~dp0.."
powershell -ExecutionPolicy Bypass -File "%~dp0run_bot.ps1"
pause
