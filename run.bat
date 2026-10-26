@echo off
rem Daily price run (the tray starts this): scrape -> classify -> report, then open the newest report.
rem The window stays 15 min (any key closes it) so you can read it; "FACEBOOK STOPPED" = open Settings > Log in to Facebook.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python run.py
for /f "delims=" %%f in ('dir /b /o-d output\pc_vs_parts_*.html 2^>nul') do (
    start "" "output\%%f"
    goto opened
)
:opened
timeout /t 900
