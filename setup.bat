@echo off
rem One-time setup: Python packages, then Start with Windows + tray + the Settings window.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.10 or newer is needed: https://www.python.org/downloads/ & pause & exit /b 1)
python -m pip install -r requirements.txt || (echo Installing packages failed, see above. & pause & exit /b 1)
echo.
echo Opening Settings: log in to Facebook, check your keywords, then Save and close.
python settings_app.py --setup || pause
