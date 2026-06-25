#!/bin/bash
# Start CompanyChat Server
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[*] Tạo virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "[*] Cài đặt dependencies..."
pip install -q -r requirements.txt

echo ""
echo "==================================="
echo "   CompanyChat Server v1.0"
echo "==================================="

# Get local IP
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo " Server  : http://$LOCAL_IP:8000"
echo " Admin   : http://$LOCAL_IP:8000/admin"
echo " Login   : admin / 123456"
echo "==================================="
echo ""

python main.py
