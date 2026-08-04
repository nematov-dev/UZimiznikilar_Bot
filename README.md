# 🤖 Uzimiznikilar Bot

Telegram guruh boshqaruvi, avtomatik moderatsiya va rejalashtirilgan xabarlar uchun to'liq funksional bot.

**Texnologiyalar:** Python 3.11+ · aiogram 3.x · PostgreSQL · imagehash

---

## Mundarija

- [Xususiyatlar](#xususiyatlar)
- [Loyiha tuzilmasi](#loyiha-tuzilmasi)
- [O'rnatish](#ornatish)
- [Sozlash (.env)](#sozlash-env)
- [Ma'lumotlar bazasi](#malumotlar-bazasi)
- [Botni ishga tushirish](#botni-ishga-tushirish)
- [Admin panel (PM)](#admin-panel-pm)
- [Guruh buyruqlari](#guruh-buyruqlari)
- [Avtomatik moderatsiya](#avtomatik-moderatsiya)
- [Taqiqlangan rasmlar](#taqiqlangan-rasmlar)
- [Taqiqlangan stiker to'plamlari](#taqiqlangan-stiker-toplamlari)
- [Rejalashtirilgan xabarlar](#rejalashtirilgan-xabarlar)
- [Tez-tez uchraydigan xatolar](#tez-tez-uchraydigan-xatolar)

---

## Xususiyatlar

### Guruh moderatsiyasi (avtomatik)
- Havolalar va reklama xabarlarini avtomatik o'chiradi
- Taqiqlangan so'zlar (substring tekshiruvi) bo'lsa o'chiradi
- Kanaldan yozilgan xabarlarni o'chiradi
- Guruhda bot tomonidan yozilgan xabarni o'chirib, o'sha botni banlab qo'yadi
- Kirish/chiqish xabarlarini o'chiradi (sozlamada yoqilganda)

- Taqiqlangan so'z yoki rasm yuborsa — foydalanuvchining guruhdagi barcha xabarlari o'chirilib, umrbod yozolmaydigan qilinadi

### Taqiqlangan rasmlar (pHash + segment hashes)
- Admin PM ga rasm yuboradi → bot saqlaydi
- Guruhda kimdir o'sha rasmni yuborganda — avtomatik o'chiriladi va yuboruvchi restrict qilinadi
- **pHash** — bir xil rasm o'lcham o'zgartirilgan yoki siqilsa ham aniqlanadi
- **Segment hash (3x3 grid)** — kesilgan yoki screenshotga olingan rasm ham aniqlanadi
- Admin panelda ro'yxat, qo'shish va o'chirish

### Taqiqlangan stiker to'plamlari
- `/banset` — reply qilingan stikerning to'plamini blacklistga qo'shadi
- Guruhda shu to'plamdan stiker yuborilsa — avtomatik o'chiriladi

### Guruh admin buyruqlari
`/ban`, `/unban`, `/kick`, `/mute`, `/unmute`, `/warn`, `/del`, `/clear`, `/info`, `/rules`, `/banimage`, `/unbanimage`, `/banset`, `/unbanset`

### Admin PM menyusi
- Statistika ko'rish
- Taqiqlangan so'zlar qo'shish/o'chirish
- Taqiqlangan rasmlar boshqaruvi
- Guruh sozlamalari (har bir guruh uchun alohida togglelar)
- Broadcast — foydalanuvchilar, guruhlar yoki hammaga
- Rejalashtirilgan xabarlar boshqaruvi
- Adminlar boshqaruvi

### Rejalashtirilgan xabarlar
- Har kun belgilangan vaqtlarda guruhga xabar yuboradi
- Bir nechta guruh tanlash (inline multi-select)
- Kuniga bir necha marta yuborish
- Faollashtirish/faolsizlashtirish, tahrirlash, o'chirish

---

## Loyiha tuzilmasi

```
Uzimiznikilar_bot/
├── .env                             # Maxfiy sozlamalar
├── .env.example                     # Namuna sozlamalar
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── bot/
│   ├── main.py                      # Entry point — polling, routerlar
│   ├── config.py                    # Pydantic settings
│   │
│   ├── handlers/
│   │   ├── admin_handler.py         # PM: admin menyusi, broadcast, sozlamalar,
│   │   │                            #     taqiqlangan rasmlar boshqaruvi
│   │   ├── scheduled_posts.py       # PM: rejalashtirilgan xabarlar (FSM)
│   │   ├── group_commands.py        # Guruh: /ban /mute /warn /banimage va h.k.
│   │   └── group_moderation.py      # Guruh: join/leave xabarlarini o'chirish
│   │
│   ├── middlewares/
│   │   └── moderation.py            # Outer middleware: har xabar tekshiruvi
│   │                                #   (havola, so'z, taqiqlangan rasm/stiker)
│   │
│   └── services/
│       ├── moderation.py            # URL pattern, taqiqlangan so'z tekshiruvi
│       ├── image_hash.py            # pHash + segment hashes (taqiqlangan rasmlar)
│       └── scheduler.py             # Kunlik xabar yuborish background loop
│
└── database/
    ├── connection.py                # asyncpg connection pool
    ├── queries.py                   # Barcha DB so'rovlar
    ├── init.sql                     # Asosiy jadvallar (birinchi marta)
    ├── migrate_scheduled_posts.sql  # scheduled_posts jadvali
    ├── migrate_nsfw.sql             # anti_nsfw ustuni
    ├── migrate_banned_images.sql    # banned_images jadvali
    ├── migrate_banned_images_v2.sql # segment_hashes ustuni
    └── migrate_remove_ai.sql        # AI (Groq/RAG) jadval/ustunlarini o'chirish
```

---

## O'rnatish

### Talablar

- Python 3.11 yoki yuqori
- PostgreSQL 14+

### 1. Reponi klonlash

```bash
git clone <repo_url>
cd Uzimiznikilar_bot
```

### 2. Virtual muhit yaratish

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

---

## Sozlash (.env)

`.env.example` faylini nusxalab, `.env` nomi bilan saqlang:

```bash
cp .env.example .env
```

Keyin quyidagi qiymatlarni to'ldiring:

```env
# --- Telegram ---
BOT_TOKEN=8159954770:AAEH...          # @BotFather dan olingan token
ADMIN_IDS=5802365587                  # Admin Telegram ID (vergul bilan bir nechtasi)

# --- PostgreSQL ---
DATABASE_URL=postgresql://postgres:1234@localhost:5432/aiogram
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aiogram
DB_USER=postgres
DB_PASSWORD=1234

# --- Bot sozlamalari ---
MAX_WARNINGS=3
MUTE_DURATION_MINUTES=60
```

---

## Ma'lumotlar bazasi

### Jadvallarni yaratish (tartib muhim)

```bash
# 1. Asosiy jadvallar (birinchi marta)
psql -U postgres -d aiogram -f database/init.sql

# 2. Rejalashtirilgan xabarlar
psql -U postgres -d aiogram -f database/migrate_scheduled_posts.sql

# 3. NSFW/stiker filtri ustuni
psql -U postgres -d aiogram -f database/migrate_nsfw.sql

# 4. Taqiqlangan rasmlar (pHash)
psql -U postgres -d aiogram -f database/migrate_banned_images.sql

# 5. Segment hashes ustuni (kesib yuborilgan/screenshot rasmlar uchun)
psql -U postgres -d aiogram -f database/migrate_banned_images_v2.sql

# 6. Eski o'rnatishda AI (Groq/RAG) qoldiqlarini tozalash (faqat mavjud DB uchun)
psql -U postgres -d aiogram -f database/migrate_remove_ai.sql
```

### Jadvallar ro'yxati

| Jadval | Maqsad |
|---|---|
| `users` | Bot foydalanuvchilari, ban/warn holati |
| `groups` | Botga qo'shilgan guruhlar va sozlamalari |
| `group_members` | Guruh a'zolari |
| `muted_users` | Vaqtincha jimlatilgan foydalanuvchilar |
| `messages` | Xabar logi (o'chirilganlar bilan) |
| `banned_words` | Taqiqlangan so'zlar ro'yxati |
| `banned_images` | Taqiqlangan rasmlar (phash + segment_hashes) |
| `broadcasts` | Yuborilgan broadcast tarixi |
| `admin_actions` | Admin harakatlari logi |
| `bot_settings` | Kalit-qiymat sozlamalar |
| `scheduled_posts` | Rejalashtirilgan xabarlar |

---

## Botni ishga tushirish

```bash
# Virtual muhit faollashgan holda
python -m bot.main
```

Muvaffaqiyatli ishga tushganda log:
```
INFO | Bot ishga tushmoqda...
INFO | Bot ishga tushdi: @your_bot_username
INFO | Scheduler ishga tushdi
INFO | Polling boshlandi...
```

---

## Admin panel (PM)

Botga shaxsiy xabar yozing — admin bo'lsangiz menyu chiqadi.

### Asosiy menyu

```
📊 Statistika          🚫 Taqiqlangan so'zlar
🏘️ Guruhlar            📢 Xabar yuborish
📅 Rejalashtirilgan xabarlar  🖼 Taqiqlangan rasmlar
👤 Adminlar boshqaruvi
```

### Statistika
Jami foydalanuvchilar / banlangan, faol guruhlar, bugungi xabarlar / o'chirilganlar.

### Taqiqlangan so'zlar
So'zlar ro'yxati, yangi qo'shish, o'chirish (inline tasdiqlash).

### Taqiqlangan rasmlar
- Botga PM da rasm yuboring → "Taqiqlasinmi?" deb so'raydi
- "Taqiqlash" → rasm saqlanadi; guruhda kim yuborsa avtomatik o'chiriladi
- Ro'yxatda har bir rasm yonida 🗑 tugmasi bor
- "➕ Rasm qo'shish" — yangi rasm qo'shish rejimi
- "🗑 Hammasini o'chirish" — ro'yxatni to'liq tozalash

### Guruh sozlamalari
Har bir guruh uchun alohida toggle:

| Toggle | Ta'rif |
|---|---|
| `anti_links` | Havola/reklama bo'lsa o'chirish |
| `anti_profanity` | Taqiqlangan so'z bo'lsa — foydalanuvchining hamma xabarini o'chirib, restrict qilish |
| `anti_nsfw` | Taqiqlangan stiker to'plami bo'lsa o'chirish |
| `delete_join_leave` | Kirish/chiqish xabarlarni o'chirish |

### Broadcast
Nishon tanlang (Foydalanuvchilar / Guruhlar / Hammaga) → xabar yozing → yuborilgach natija ko'rsatiladi.

---

## Guruh buyruqlari

Bot guruhda **admin** bo'lishi shart. Buyruqlar reply yoki `@username` bilan ishlaydi.

| Buyruq | Ta'rif |
|---|---|
| `/ban [sabab]` | Foydalanuvchini ban qilish |
| `/unban` | Banni olib tashlash |
| `/kick` | Guruhdan chiqarish (ban emas) |
| `/mute [daqiqa]` | Vaqtincha jimlatish |
| `/unmute` | Jimlatishni bekor qilish |
| `/warn [sabab]` | Ogohlantirish (3 ta → avtomatik ban) |
| `/del` | Reply qilingan xabarni o'chirish |
| `/clear [N]` | So'nggi N ta xabarni o'chirish (max 100) |
| `/info` | Foydalanuvchi haqida ma'lumot |
| `/rules` | Guruh qoidalari |
| `/banimage [izoh]` | Reply qilingan rasmni taqiqlash |
| `/unbanimage` | Reply qilingan rasmdan taqiqni olib tashlash |
| `/banset` | Reply qilingan stiker to'plamini bloklash |
| `/unbanset` | Reply qilingan stiker to'plamini blokdan chiqarish |

---

## Avtomatik moderatsiya

Moderatsiya **outer middleware** orqali ishlaydi — barcha xabarlarga handler topilmasa ham qo'llaniladi.

### Tekshiruv tartibi

```
Xabar keldi
    |
    +-- Kanaldan yuborilganmi? --> o'chir
    +-- Bot yubordi? --> botni ban qil + o'chir
    |
    +-- Foydalanuvchi xabari (admin emas):
            +-- anti_links yoqilgan va havola bor? --> o'chir
            +-- anti_profanity yoqilgan va taqiq so'z? --> hamma xabarini o'chir + restrict
            +-- Taqiqlangan rasm? --> hamma xabarini o'chir + restrict
            +-- anti_nsfw yoqilgan va taqiqlangan stiker to'plami? --> o'chir
```

### Havola aniqlash

Quyidagilarni bloklaydi: `https://`, `http://`, `www.`, `t.me/`, `.com`, `.net`, `.org`, `.uz`, `.io`, `.me`, `.shop`, `.online` va boshqalar. `@username` eslatmalari bloklanmaydi.

---

## Taqiqlangan rasmlar

### Qanday ishlaydi

Bot rasmni ikki usulda saqlaydi va ikkala usul bilan tekshiradi:

**1. pHash (perceptual hash)**
Butun rasmning "barmoq izi". Rasm o'lchamlari o'zgartirilsa yoki siqilsa ham bir xil hash chiqadi. Hamming masofasi ≤ 8 bo'lsa — bir xil rasm hisoblanadi.

**2. Segment hashes (3x3 grid)**
Rasm 9 ta bo'lakka bo'linadi, har birining pHash hisoblanadi. Agar kelayotgan rasmda kamida 2 ta bo'lak taqiqlangan rasmga mos kelsa (Hamming ≤ 6) — ban rasm sifatida aniqlanadi.

Bu ikkinchi usul quyidagi holatlarda ham ishlaydi:
- Taqiqlangan rasm kesilgan (crop) holda yuborilsa
- Taqiqlangan rasm screenshotning ichida bo'lsa (atrofida boshqa kontent bilan)
- Taqiqlangan rasmning chegaralari biroz o'zgartirilsa

### Qo'shish usullari

**PM orqali:**
1. Botga PM da rasm yuboring
2. "Taqiqlasinmi?" so'roviga "Taqiqlash" tugmasini bosing

**Guruhda buyruq orqali:**
```
# Rasmga reply qilib:
/banimage
/banimage haqoratli rasm
```

### Cache

Taqiqlangan rasmlar xotirada keshlanadi — har xabarda DB ga murojaat yo'q. Yangi rasm qo'shilganda yoki o'chirilganda kesh avtomatik yangilanadi.

---

## Taqiqlangan stiker to'plamlari

Admin stikerga reply qilib `/banset` yozsa, o'sha stiker to'plamining `set_name`i `bot_settings` ga yoziladi. Guruh sozlamalarida `anti_nsfw` toggle bilan boshqariladi. `/unbanset` — blokdan chiqaradi.

---

## Rejalashtirilgan xabarlar

Admin PM → **📅 Rejalashtirilgan xabarlar**.

### Yangi post yaratish

1. **Guruhlarni tanlang** — ko'p tanlash mumkin
2. **Sarlavha** — admin panelda ko'rsatish uchun
3. **Matn** — guruhga yuboriladigan kontent (HTML formatda)
4. **Kunlik yuborish soni** — raqam
5. **Vaqtlar** — `HH:MM` formatida (masalan: `09:00`, `18:30`)

### Post boshqaruvi

Ko'rish, faollashtirish/o'chirish, tahrirlash (sarlavha + matn), o'chirish (tasdiqlash bilan).

### Scheduler

Background loop har daqiqada ishlaydi, joriy `HH:MM` ni post vaqtlari bilan solishtiradi. Yarim tunda log tozalanadi.

---

## Tez-tez uchraydigan xatolar

### Bot guruhda ishlamayapti
1. Bot guruhda **admin** ekanligini tekshiring (xabar o'chirish, ban qilish huquqi)
2. `dp.message.outer_middleware(BotMiddleware())` — `outer_middleware` bo'lishi shart

### `relation "banned_images" does not exist`
```bash
psql -U postgres -d aiogram -f database/migrate_banned_images.sql
psql -U postgres -d aiogram -f database/migrate_banned_images_v2.sql
```

### `column "segment_hashes" does not exist`
```bash
psql -U postgres -d aiogram -f database/migrate_banned_images_v2.sql
```

### `ModuleNotFoundError: No module named 'imagehash'`
```bash
pip install imagehash Pillow
```

### Rasm taqiqlandi lekin guruhda o'chirilmayapti
1. v2 migratsiya (`segment_hashes` ustuni) ishga tushirilganini tekshiring
2. Botni restart qiling — kesh yangilanadi

### FSM holati ishlamayapti (rejalashtirilgan xabarlar)
`admin_handler.py` da `pm_fallback` dekoratorida `StateFilter(None)` bo'lishi shart.

---

## Litsenziya

MIT — erkin foydalanishingiz mumkin.
