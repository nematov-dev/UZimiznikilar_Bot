#!/bin/bash
# Quick setup script

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "📋 Copying .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  .env fayli yaratildi. Iltimos to'ldiring!"
fi

echo "🐳 Starting PostgreSQL & Redis..."
docker-compose up -d postgres redis

echo "⏳ Waiting for PostgreSQL..."
sleep 5

echo "✅ Setup complete!"
echo ""
echo "Keyingi qadamlar:"
echo "1. .env faylini to'ldiring (BOT_TOKEN, GOOGLE_PROJECT_ID va boshqalar)"
echo "2. python -m bot.main   — botni ishga tushirish"
echo "3. python -m admin_panel.app   — admin panelni ishga tushirish"
