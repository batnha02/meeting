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

echo [*] Khoi dong CompanyChat...
python main.py
pause
