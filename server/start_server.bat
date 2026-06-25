@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".venv" (
    echo [*] Tao virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [*] Cai dat dependencies...
pip install -q -r requirements.txt

echo.
echo ===================================
echo    CompanyChat Server v1.0
echo ===================================
echo  Admin: http://localhost:8000/admin
echo  Login: admin / 123456
echo ===================================
echo.

python main.py
pause
