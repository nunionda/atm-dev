#!/bin/bash
set -e

echo "[Setup] Installing Python dependencies..."
pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt

echo "[Setup] Installing Node dependencies..."
cd web && npm install && cd ..

echo "[Setup] Initializing database..."
python3 main.py init-db 2>/dev/null || true

echo "[Setup] Ready for development."
