# Server ga o'rnatish qo'llanmasi

Ubuntu 22.04 VPS ga ketma-ket o'rnatish.

---

## 1. Serverga ulanish

```bash
ssh root@YOUR_SERVER_IP
```

---

## 2. Tizimni yangilash

```bash
apt update && apt upgrade -y
```

---

## 3. Python 3.11 o'rnatish

```bash
apt install -y software-properties-common
add-apt-repository ppa:deadsnakes/ppa -y
apt update
apt install -y python3.11 python3.11-venv python3.11-dev python3-pip
```

Tekshirish:
```bash
python3.11 --version
```

---

## 4. PostgreSQL o'rnatish

```bash
apt install -y postgresql postgresql-contrib

# Ishga tushirish
systemctl start postgresql
systemctl enable postgresql
```

### Ma'lumotlar bazasi va foydalanuvchi yaratish

```bash
sudo -u postgres psql
```

psql ichida:
```sql
CREATE DATABASE aiogram;
CREATE USER botuser WITH PASSWORD 'KUCHLI_PAROL';
GRANT ALL PRIVILEGES ON DATABASE aiogram TO botuser;
\q
```

---

## 5. Git o'rnatish va kodni yuklash

```bash
apt install -y git
```

### Variant A — GitHub/GitLab dan

```bash
cd /opt
git clone https://github.com/SIZNING_REPO/Uzimiznikilar_bot.git
cd Uzimiznikilar_bot
```

### Variant B — lokal kompyuterdan scp bilan

Lokal terminalda (Windows PowerShell yoki macOS Terminal):
```bash
scp -r D:\projects\Uzimiznikilar_bot root@YOUR_SERVER_IP:/opt/
```

Keyin serverda:
```bash
cd /opt/Uzimiznikilar_bot
```

---

## 6. Virtual muhit va kutubxonalar

```bash
python3.11 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Agar imagehash alohida kerak bo'lsa:
```bash
pip install imagehash Pillow
```

---

## 7. .env faylini sozlash

```bash
cp .env.example .env
nano .env
```

Quyidagilarni to'ldiring:

```env
BOT_TOKEN=8159954770:AAEH...
ADMIN_IDS=5802365587

DATABASE_URL=postgresql://botuser:KUCHLI_PAROL@localhost:5432/aiogram
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aiogram
DB_USER=botuser
DB_PASSWORD=KUCHLI_PAROL

MAX_WARNINGS=3
MUTE_DURATION_MINUTES=60
```

Saqlash: `Ctrl+O` → `Enter` → `Ctrl+X`

---

## 8. Ma'lumotlar bazasi jadvallarini yaratish

```bash
source .venv/bin/activate

# psql bilan ulanish
PGPASSWORD=KUCHLI_PAROL psql -U botuser -d aiogram -h localhost -f database/init.sql
PGPASSWORD=KUCHLI_PAROL psql -U botuser -d aiogram -h localhost -f database/migrate_scheduled_posts.sql
PGPASSWORD=KUCHLI_PAROL psql -U botuser -d aiogram -h localhost -f database/migrate_nsfw.sql
PGPASSWORD=KUCHLI_PAROL psql -U botuser -d aiogram -h localhost -f database/migrate_banned_images.sql
PGPASSWORD=KUCHLI_PAROL psql -U botuser -d aiogram -h localhost -f database/migrate_banned_images_v2.sql
```

Eski o'rnatishda AI (Groq/RAG) qoldiqlari bo'lsa, tozalash uchun:
```bash
PGPASSWORD=KUCHLI_PAROL psql -U botuser -d aiogram -h localhost -f database/migrate_remove_ai.sql
```

Tekshirish (jadvallar bor-yo'qligini ko'rish):
```bash
PGPASSWORD=KUCHLI_PAROL psql -U botuser -d aiogram -h localhost -c "\dt"
```

---

## 9. Botni test sifatida ishga tushirish

```bash
source .venv/bin/activate
python -m bot.main
```

Log chiqsa va xato bo'lmasa — to'xtatib, keyingi qadamga o'ting (`Ctrl+C`).

---

## 10. Systemd xizmati yaratish (avtomatik ishga tushish)

```bash
nano /etc/systemd/system/uzimiznikilar-bot.service
```

Quyidagini yozing:

```ini
[Unit]
Description=Uzimiznikilar Telegram Bot
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/Uzimiznikilar_bot
EnvironmentFile=/opt/Uzimiznikilar_bot/.env
ExecStart=/opt/Uzimiznikilar_bot/.venv/bin/python -m bot.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Saqlash: `Ctrl+O` → `Enter` → `Ctrl+X`

### Xizmatni yoqish va ishga tushirish

```bash
systemctl daemon-reload
systemctl enable uzimiznikilar-bot
systemctl start uzimiznikilar-bot
```

---

## 11. Bot holatini tekshirish

```bash
# Holat
systemctl status uzimiznikilar-bot

# Loglar (oxirgi 50 qator)
journalctl -u uzimiznikilar-bot -n 50

# Loglarni jonli kuzatish
journalctl -u uzimiznikilar-bot -f
```

---

## Foydali buyruqlar

| Vazifa | Buyruq |
|---|---|
| Botni to'xtatish | `systemctl stop uzimiznikilar-bot` |
| Botni qayta ishga tushirish | `systemctl restart uzimiznikilar-bot` |
| Loglarni ko'rish | `journalctl -u uzimiznikilar-bot -f` |
| Kodni yangilash (git) | `cd /opt/Uzimiznikilar_bot && git pull && systemctl restart uzimiznikilar-bot` |

---

## Kodni yangilash (keyingi safar)

### GitHub dan:
```bash
cd /opt/Uzimiznikilar_bot
git pull
source .venv/bin/activate
pip install -r requirements.txt   # agar yangi kutubxona qo'shilgan bo'lsa
systemctl restart uzimiznikilar-bot
```

### scp bilan:
```bash
# Lokal kompyuterda:
scp -r D:\projects\Uzimiznikilar_bot\bot root@YOUR_SERVER_IP:/opt/Uzimiznikilar_bot/

# Serverda:
systemctl restart uzimiznikilar-bot
```

---

## Xatolar va yechimlar

### `connection refused` (PostgreSQL)
```bash
systemctl status postgresql
systemctl start postgresql
```

### `permission denied` (fayl)
```bash
chown -R root:root /opt/Uzimiznikilar_bot
chmod -R 755 /opt/Uzimiznikilar_bot
```

### Bot ishga tushmayapti — log ko'rish
```bash
journalctl -u uzimiznikilar-bot -n 100 --no-pager
```

### `.env` o'zgartirilsa
```bash
systemctl restart uzimiznikilar-bot
```
