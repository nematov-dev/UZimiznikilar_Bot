# 🤖 Uzimiznikilar Bot

Telegram guruh boshqaruvi, avtomatik moderatsiya, AI yordamchi va rejalashtirilgan xabarlar uchun to'liq funksional bot.

**Texnologiyalar:** Python 3.11+ · aiogram 3.x · PostgreSQL · Groq AI (LLaMA 3.3) · imagehash · NudeNet · opennsfw2

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
- [18+ kontent filtri (NSFW)](#18-kontent-filtri-nsfw)
- [AI va RAG tizimi](#ai-va-rag-tizimi)
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

### Taqiqlangan rasmlar (pHash + segment hashes)
- Admin PM ga rasm yuboradi → bot saqlaydi
- Guruhda kimdir o'sha rasmni yuborganda — avtomatik o'chiriladi
- **pHash** — bir xil rasm o'lcham o'zgartirilgan yoki siqilsa ham aniqlanadi
- **Segment hash (3x3 grid)** — kesilgan yoki screenshotga olingan rasm ham aniqlanadi
- Admin panelda ro'yxat, qo'shish va o'chirish

### 18+ kontent filtri (NSFW)
- Dual model: NudeNet + opennsfw2
- Rasm, GIF, stiker tekshiriladi
- Har guruh uchun alohida on/off

### Guruh admin buyruqlari
`/ban`, `/unban`, `/kick`, `/mute`, `/unmute`, `/warn`, `/del`, `/clear`, `/info`, `/rules`, `/banimage`, `/unbanimage`, `/banset`

### Admin PM menyusi
- Statistika ko'rish
- Taqiqlangan so'zlar qo'shish/o'chirish
- Taqiqlangan rasmlar boshqaruvi
- Guruh sozlamalari (har bir guruh uchun alohida togglelar)
- Broadcast — foydalanuvchilar, guruhlar yoki hammaga
- AI tizim promptini o'zgartirish
- Rejalashtirilgan xabarlar boshqaruvi
- Adminlar boshqaruvi

### AI yordamchi (Groq / LLaMA 3.3)
- Guruhda `@bot_username savol` yoki `/ai savol` — tez javob (45 soniya timeout)
- RAG: admin yuklagan hujjatlar (PDF/DOCX/TXT) asosida javob (PM da)
- Guruhda to'g'ridan-to'g'ri Groq API orqali tez javob
- Non-admin PM → AI javob (fallback)

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
│   │   ├── group_moderation.py      # Guruh: join/leave xabarlarini o'chirish
│   │   └── rag_handler.py           # Hujjat yuklash + AI javob (guruh va PM)
│   │
│   ├── middlewares/
│   │   └── moderation.py            # Outer middleware: har xabar tekshiruvi
│   │                                #   (havola, so'z, NSFW, taqiqlangan rasm)
│   │
│   └── services/
│       ├── moderation.py            # URL pattern, taqiqlangan so'z tekshiruvi
│       ├── groq_ai.py               # Groq API (LLaMA 3.3) wrapper
│       ├── rag_service.py           # RAG pipeline (embed → search → generate)
│       ├── image_hash.py            # pHash + segment hashes (taqiqlangan rasmlar)
│       ├── nsfw_checker.py          # Dual model NSFW tekshiruvi
│       ├── scheduler.py             # Kunlik xabar yuborish background loop
│       └── vertex_ai.py             # (legacy) Vertex AI embedding
│
└── database/
    ├── connection.py                # asyncpg connection pool
    ├── queries.py                   # Barcha DB so'rovlar
    ├── init.sql                     # Asosiy jadvallar (birinchi marta)
    ├── migrate_scheduled_posts.sql  # scheduled_posts jadvali
    ├── migrate_groq.sql             # Groq AI uchun bot_settings
    ├── migrate_nsfw.sql             # anti_nsfw ustuni
    ├── migrate_banned_images.sql    # banned_images jadvali
    └── migrate_banned_images_v2.sql # segment_hashes ustuni
```

---

## O'rnatish

### Talablar

- Python 3.11 yoki yuqori
- PostgreSQL 14+
- Groq API kalit (bepul: [console.groq.com](https://console.groq.com))

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

# --- Groq AI ---
GROQ_API_KEY=gsk_...                  # console.groq.com dan olingan kalit

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

# 3. Groq AI sozlamalari
psql -U postgres -d aiogram -f database/migrate_groq.sql

# 4. NSFW filtri ustuni
psql -U postgres -d aiogram -f database/migrate_nsfw.sql

# 5. Taqiqlangan rasmlar (pHash)
psql -U postgres -d aiogram -f database/migrate_banned_images.sql

# 6. Segment hashes ustuni (kesib yuborilgan/screenshot rasmlar uchun)
psql -U postgres -d aiogram -f database/migrate_banned_images_v2.sql
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
| `documents` | Admin yuklagan hujjatlar |
| `document_chunks` | Hujjat bo'laklari + vektorlar (pgvector) |
| `broadcasts` | Yuborilgan broadcast tarixi |
| `admin_actions` | Admin harakatlari logi |
| `bot_settings` | Kalit-qiymat sozlamalar (AI prompt va h.k.) |
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
📅 Rejalashtirilgan xabarlar
🖼 Taqiqlangan rasmlar  ⚙️ Sozlamalar
👤 Adminlar boshqaruvi
```

### Statistika
Jami foydalanuvchilar / banlangan, faol guruhlar, bugungi xabarlar / o'chirilganlar, yuklangan hujjatlar.

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
| `anti_links` | Havola bo'lsa o'chirish |
| `anti_profanity` | Taqiqlangan so'z bo'lsa o'chirish |
| `anti_nsfw` | 18+ kontent (rasm/gif/stiker) bo'lsa o'chirish |
| `delete_join_leave` | Kirish/chiqish xabarlarni o'chirish |
| `ai_enabled` | AI javoblarni yoqish/o'chirish |

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
| `/ai [savol]` | AI yordamchiga savol |
| `/banimage [izoh]` | Reply qilingan rasmni taqiqlash |
| `/unbanimage` | Reply qilingan rasmdan taqiqni olib tashlash |
| `/banset` | Stiker to'plamini bloklash/blokdan chiqarish |

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
            +-- anti_profanity yoqilgan va taqiq so'z? --> o'chir
            +-- anti_nsfw yoqilgan va 18+ rasm/gif/stiker? --> o'chir
            +-- Taqiqlangan rasm? --> o'chir
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

## 18+ kontent filtri (NSFW)

Dual model tizimi:

| Model | Vazifasi |
|---|---|
| **NudeNet** | Anatomik aniqlash |
| **opennsfw2** | Umumiy NSFW klassifikatsiya |

Ikkala model natijasi birlashtirilib threshold bo'yicha qaror qabul qilinadi. Guruh sozlamalarida `anti_nsfw` toggle bilan boshqariladi.

Tekshiriladigan tarkib: `photo`, `animation` (GIF), `sticker`.

---

## AI va RAG tizimi

### Guruhda ishlatish

```
@your_bot_username bu haqida nima deyilgan?
/ai Uzimiznikilar loyihasi nima?
```

Guruh AI to'g'ridan-to'g'ri **Groq API** (LLaMA 3.3 70B) orqali ishlaydi.

### Hujjat yuklash (admin PM)

1. Botga PDF, DOCX yoki TXT fayl yuboring
2. Bot bo'laklarga ajratib, vektorlaydi → pgvector ga saqlaydi
3. PM da savol berilganda: savol vektorlashadi → eng yaqin bo'laklar → Groq kontekst bilan javob beradi

### Javob vaqtlari

| Holat | Usul | Timeout |
|---|---|---|
| Guruh AI | Groq to'g'ridan-to'g'ri | 45 soniya |
| PM AI (hujjatsiz) | Groq to'g'ridan-to'g'ri | 60 soniya |
| PM AI (hujjat bilan) | RAG + Groq | 60 soniya |

Timeout bo'lsa: `"Javob vaqt tugdi. Iltimos, qayta urinib ko'ring."`

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

### `ModuleNotFoundError: No module named 'nudenet'`
```bash
pip install nudenet opennsfw2
```

### Rasm taqiqlandi lekin guruhda o'chirilmayapti
1. v2 migratsiya (`segment_hashes` ustuni) ishga tushirilganini tekshiring
2. Botni restart qiling — kesh yangilanadi

### FSM holati ishlamayapti (rejalashtirilgan xabarlar)
`admin_handler.py` da `pm_fallback` dekoratorida `StateFilter(None)` bo'lishi shart.

---

## Litsenziya

MIT — erkin foydalanishingiz mumkin.
