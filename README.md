# 💬 Real-time Private Chat — Django Channels + Redis

O‘quv loyihasi: ikki foydalanuvchi WebSocket orqali real vaqtda yozishadi.
Xabar yuborilgan zahoti ikkinchi userga yetib boradi, sahifani yangilash shart emas.

**Imkoniyatlar:** ro‘yxatdan o‘tish/login/logout · userlar ro‘yxati · private chat ·
chat tarixi DB’da · Online/Offline · "is typing..." · xabar vaqti · ✓ / ✓✓ (o‘qildi) ·
o‘qilmagan xabarlar soni (badge) · Redis Channel Layer.

---

## 0. Mundarija

1. [Nazariya](#1-nazariya)
2. [Project structure](#2-project-structure)
3. [O‘rnatish va ishga tushirish](#3-ornatish-va-ishga-tushirish)
4. [Bosqich 1 — Backend](#4-bosqich-1--backend-models-api)
5. [Bosqich 2 — WebSocket](#5-bosqich-2--websocket)
6. [Bosqich 3 — Frontend](#6-bosqich-3--frontend)
7. [Xavfsizlik](#7-xavfsizlik)
8. [Test qilish](#8-test-qilish)
9. [Loyiha qanday ishlaydi (qisqacha)](#9-loyiha-qanday-ishlaydi)
10. [Amaliy vazifalar](#10-amaliy-vazifalar)

---

## 1. Nazariya

### WebSocket nima?
Brauzer va server o‘rtasidagi **doimiy ochiq, ikki tomonlama** aloqa kanali.
Bir marta ulanasiz, keyin ikkala tomon ham istalgan paytda xabar yubora oladi.

### HTTP va WebSocket farqi

| | HTTP | WebSocket |
|---|---|---|
| Aloqa | So‘rov → javob → connection yopiladi | Ulanish ochiq qoladi |
| Kim boshlaydi | Faqat klient | Ikkala tomon ham |
| Server o‘zi xabar yubora oladimi? | Yo‘q | **Ha** |
| Manzil | `http://`, `https://` | `ws://`, `wss://` |
| Qachon | Sahifa, forma, REST API | Chat, bildirishnoma, o‘yin, live dashboard |

Analogiya: HTTP — **SMS** (har safar yangi xabar, javobni kutish). WebSocket — **telefon qo‘ng‘irog‘i** (liniya ochiq, ikkalangiz ham gapira olasiz).

HTTP bilan chat qilish uchun brauzer har 1 soniyada "yangi xabar bormi?" deb so‘rashi kerak bo‘lardi (*polling*). Bu serverni bekorga yuklaydi va baribir kechikadi.

WebSocket HTTP so‘rov bilan boshlanadi (`Upgrade: websocket` header). Server `101 Switching Protocols` deb javob beradi va shu TCP connection WebSocket’ga aylanadi. Shuning uchun session cookie ham yuboriladi, biz userni aynan shu orqali taniymiz.

### ASGI nima?
- **WSGI** — Django’ning eski interfeysi: *1 so‘rov → 1 javob*, sinxron. WebSocket’ni qo‘llamaydi.
- **ASGI** (*Asynchronous Server Gateway Interface*) — yangi interfeys: asinxron, uzoq yashaydigan connectionlarni (WebSocket) qo‘llaydi.
- ASGI server: **Daphne**, Uvicorn. Biz `daphne`ni `INSTALLED_APPS`ning boshiga qo‘yganmiz, shuning uchun `runserver` ASGI rejimida ishlaydi.

### Django Channels nima?
Django’ni HTTP’dan tashqari WebSocket bilan ham ishlashga o‘rgatadigan kutubxona. U quyidagilarni beradi:
**Consumer** (WebSocket uchun view), **Routing** (WebSocket uchun urls), **Channel Layer** (connectionlar orasida xabar almashish), **AuthMiddleware** (session orqali user).

### Consumer nima?
WebSocket uchun "view". Oddiy view bitta so‘rovga javob beradi. Consumer esa connection yashagan butun vaqt davomida ishlaydi:

```python
async def connect(self): ...                       # ulanish
async def receive(self, text_data): ...            # brauzerdan xabar keldi
async def disconnect(self, close_code): ...        # ulanish yopildi
```

Har bir brauzer tabi uchun consumer’ning **alohida nusxasi** yaratiladi va har biriga noyob `self.channel_name` beriladi.

### Routing nima?
URL → consumer bog‘lanishi (`chat/routing.py`):
```python
re_path(r"^ws/chat/(?P<user_id>\d+)/$", ChatConsumer.as_asgi())
```
`config/asgi.py`dagi `ProtocolTypeRouter` so‘rov turiga qarab yo‘naltiradi: `http` → Django view’lari, `websocket` → Channels.

### Channel Layer nima?
Consumerlar bir-biriga xabar yuboradigan **pochta tizimi**.

Ali va Vali alohida connectionlarda o‘tiribdi, ehtimol hatto alohida server processlarida. Ali yozgan xabar Vali’ning consumer’iga qanday yetadi? Channel Layer orqali:

```
Ali brauzeri ──ws──▶ ChatConsumer(Ali) ──group_send("chat_7")──▶ [Redis]
                                                                   │
Vali brauzeri ◀──ws── ChatConsumer(Vali) ◀──────chat_message()─────┘
```

### Redis nima uchun kerak?
Redis — xotirada ishlaydigan juda tez ma’lumotlar ombori. Channel Layer uchun u **umumiy pochta qutisi** vazifasini bajaradi:
- Qaysi guruhda qaysi connectionlar borligini saqlaydi.
- Bir processdan ikkinchisiga xabar yetkazadi.
- `InMemoryChannelLayer` faqat bitta process ichida ishlaydi. Production’da bir nechta worker bo‘lsa, ular bir-birini "ko‘rmaydi". Redis bu muammoni hal qiladi.

### Asosiy metodlar

| Metod | Nima qiladi | Loyihadagi misol |
|---|---|---|
| `group_add(group, channel_name)` | Connectionni guruhga qo‘shadi | Ali va Vali `chat_7` guruhiga kiradi |
| `group_send(group, event)` | Guruhdagi **hamma** connectionga event yuboradi. `event["type"]` qaysi metod chaqirilishini belgilaydi (`"chat.message"` → `chat_message()`) | Yangi xabarni ikkala tomonga tarqatish |
| `group_discard(group, channel_name)` | Connectionni guruhdan chiqaradi (disconnect’da **albatta**) | Tab yopilganda |
| `receive(text_data)` | Brauzer `socket.send()` qilganda chaqiriladi | JSON’ni o‘qib, `type` bo‘yicha handlerga yo‘naltirish |
| `send(text_data)` | **Faqat shu** connectionga (bitta tabga) xabar yuboradi | `chat_message()` ichida brauzerga yuborish |

> **Muhim farq:** `send()` → bitta brauzer. `group_send()` → guruhdagi hamma consumerlarga, ular esa o‘z navbatida `send()` qiladi.

---

## 2. Project structure

```text
chat_project/
├── config/
│   ├── settings.py        # .env, DB, Channels, Redis, DRF, xavfsizlik
│   ├── urls.py            # HTTP marshrutlar
│   ├── asgi.py            # HTTP + WebSocket kirish nuqtasi
│   └── wsgi.py
├── accounts/
│   ├── models.py          # Custom User (active_connections, last_seen)
│   ├── forms.py           # RegisterForm
│   ├── views.py           # Register / Login / Logout
│   ├── urls.py
│   ├── admin.py
│   └── management/commands/reset_presence.py
├── chat/
│   ├── models.py          # Conversation, Message
│   ├── services.py        # Biznes-logika (API ham, consumer ham ishlatadi)
│   ├── serializers.py     # DRF serializerlar
│   ├── views.py           # Chat sahifasi + REST API
│   ├── urls.py
│   ├── consumers.py       # PresenceConsumer, ChatConsumer
│   ├── routing.py         # WebSocket URL’lar
│   ├── admin.py
│   └── tests/             # API va WebSocket testlari
├── templates/
│   ├── base.html
│   ├── accounts/{login,register,_form}.html
│   └── chat/index.html
├── static/
│   ├── css/style.css
│   └── js/chat.js
├── manage.py
├── requirements.txt
├── .env.example
└── .env                   # git’ga qo‘shilmaydi!
```

---

## 3. O‘rnatish va ishga tushirish

### 3.1 Redis
```bash
# macOS
brew install redis && brew services start redis
# Ubuntu
sudo apt install redis-server && sudo systemctl start redis
# Docker
docker run -d --name redis -p 6379:6379 redis:7

redis-cli ping          # -> PONG
```

### 3.2 Loyiha
```bash
cd chat_project
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env ichida SECRET_KEY ni almashtiring:
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"

python manage.py makemigrations     # (migratsiyalar tayyor, bu faqat tekshiruv)
python manage.py migrate
python manage.py createsuperuser    # admin panel uchun (ixtiyoriy)
python manage.py runserver
```

Terminalda `Starting ASGI/Daphne ... development server` yozuvi chiqishi kerak. `ASGI` so‘zi ko‘rinmasa, `daphne` `INSTALLED_APPS`da birinchi turmagan bo‘ladi.

Ochish: http://127.0.0.1:8000

### 3.3 PostgreSQL ishlatish (ixtiyoriy)
```bash
pip install "psycopg[binary]"
# .env:
DATABASE_URL=postgres://chat_user:chat_pass@127.0.0.1:5432/chat_db
python manage.py migrate
```

### 3.4 Production’da
```bash
python manage.py collectstatic
daphne -b 0.0.0.0 -p 8000 config.asgi:application
# yoki: uvicorn config.asgi:application --workers 4
```
Nginx’da WebSocket uchun `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` kerak.

---

## 4. Bosqich 1 — Backend (models, API)

### `.env` va `config/settings.py`
- `django-environ` barcha secretlarni `.env`dan o‘qiydi: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `REDIS_URL`.
- `AUTH_USER_MODEL = "accounts.User"`. Custom user modelni **birinchi migratsiyadan oldin** belgilash kerak.
- `ASGI_APPLICATION = "config.asgi.application"`.
- `CHANNEL_LAYERS` → `channels_redis.core.RedisChannelLayer`.
- DRF: `SessionAuthentication` + `IsAuthenticated`.

### `accounts/models.py` — User
`AbstractUser`ga ikkita maydon qo‘shilgan:
- `active_connections`: nechta tab ochiq. `> 0` bo‘lsa user online. Nega boolean emas? User 2 ta tab ochib, bittasini yopsa ham hali online bo‘lishi kerak.
- `last_seen`: "last seen 14:32" yozuvi uchun.

Hisoblagich `F("active_connections") + 1` bilan o‘zgartiriladi. Qiymat DB ichida o‘zgaradi, shuning uchun bir vaqtda ochilgan ikki tab bir-birining natijasini buzmaydi (*race condition*).

### `chat/models.py`
- **Conversation**(`user1`, `user2`). Qoida: doim `user1.id < user2.id`. Shunda (Ali, Vali) va (Vali, Ali) bitta suhbat bo‘ladi. DB darajasida `UniqueConstraint` va `CheckConstraint` bilan kafolatlangan.
- **Message**(`conversation`, `sender`, `content`, `created_at`, `is_read`, `read_at`).

### `chat/services.py`
`create_message`, `mark_conversation_read`, `serialize_message`. Bu funksiyalarni **ham REST API, ham WebSocket** ishlatadi, shuning uchun kod takrorlanmaydi.

### REST API (`chat/views.py`)

| Method | URL | Vazifa |
|---|---|---|
| GET | `/api/users/` | Mendan boshqa userlar + `is_online` + `unread_count` |
| GET | `/api/chat/<user_id>/messages/?before=<id>` | Oxirgi 50 ta xabar (tarix) |
| POST | `/api/chat/<user_id>/read/` | O‘qildi deb belgilash (WebSocket ishlamasa zaxira yo‘l) |

**Nega tarix HTTP orqali, WebSocket orqali emas?** Tarix bir martalik so‘rov. HTTP uchun keshlash, pagination va DRF tayyor. WebSocket faqat *real-time* hodisalar uchun.

---

## 5. Bosqich 2 — WebSocket

### `config/asgi.py`
```python
"websocket": AllowedHostsOriginValidator(      # 1. Origin tekshiruvi
    AuthMiddlewareStack(                       # 2. session cookie -> scope["user"]
        URLRouter(websocket_urlpatterns)       # 3. URL -> consumer
    )
)
```

### `chat/routing.py`
```
/ws/presence/          -> PresenceConsumer  (online status, bildirishnomalar)
/ws/chat/<user_id>/    -> ChatConsumer      (shu user bilan private chat)
```

### Guruhlar

| Guruh | Kimlar bor | Nima uchun |
|---|---|---|
| `chat_<conversation_id>` | Suhbatning 2 ishtirokchisi (barcha tablari) | xabar, typing, read |
| `presence` | Hamma online userlar | online/offline hodisasi |
| `user_<id>` | Bitta userning barcha tablari | "sizga X yozdi" → sidebar badge |

### ChatConsumer protokoli

Brauzer → Server:
```json
{"type": "chat_message", "message": "Salom"}
{"type": "typing", "is_typing": true}
{"type": "read"}
```
Server → Brauzer:
```json
{"type": "chat_message", "message": {"id": 1, "sender": 3, "content": "Salom", "created_at": "...", "is_read": false}}
{"type": "typing", "user_id": 3, "is_typing": true}
{"type": "messages_read", "reader_id": 5, "message_ids": [1, 2]}
{"type": "error", "detail": "..."}
```

### Xabar yo‘li (qadamma-qadam)
1. Ali `Send` bosadi. JS `socket.send({"type":"chat_message",...})` qiladi.
2. `ChatConsumer.receive()` JSON’ni o‘qiydi va `handle_chat_message()`ni chaqiradi.
3. `create_message()` xabarni **DB’ga saqlaydi** (`database_sync_to_async` orqali).
4. `group_send("chat_7", {"type": "chat.message", ...})` → Redis.
5. Redis guruhdagi har bir consumer’ga (Ali’niki va Vali’niki) eventni yetkazadi. Ularning `chat_message()` metodi chaqiriladi.
6. Har biri `self.send()` qiladi va brauzerda `socket.onmessage` ishlaydi.
7. Qo‘shimcha ravishda `group_send("user_<vali_id>", "notify.new_message")` yuboriladi. Vali boshqa odam bilan yozishayotgan bo‘lsa, sidebar’da badge chiqadi.

### Close kodlari

| Kod | Ma’no |
|---|---|
| 4001 | Login qilinmagan |
| 4003 | O‘zi bilan chat ochmoqchi |
| 4004 | Bunday user yo‘q |

> Consumer `accept()` qilib, **keyin** `close(code)` qiladi. `accept()`dan oldin yopilsa, brauzer faqat `1006` kodini ko‘radi va sababini bilolmaydi.

### `database_sync_to_async` nega kerak?
Consumer `async`, Django ORM esa sinxron. ORM’ni to‘g‘ridan-to‘g‘ri chaqirsak, event loop bloklanadi va boshqa hamma connectionlar kutib qoladi. Dekorator ORM kodini alohida thread’da ishga tushiradi.

---

## 6. Bosqich 3 — Frontend

- `templates/chat/index.html` — layout: chapda userlar, o‘ngda chat.
- `{{ request.user.id|json_script:"current-user-id" }}` — Python qiymatini JS’ga xavfsiz uzatadi.
- `static/js/chat.js`:
  - `loadUsers()` → `GET /api/users/`
  - `connectPresence()` → `/ws/presence/`, uzilsa **exponential backoff** bilan qayta ulanadi (1s, 2s, 4s … 30s)
  - `openChat(id)` → avval tarixni HTTP’dan oladi, keyin `/ws/chat/<id>/`ga ulanadi
  - Typing: birinchi tugma bosilganda `true`, 1.5 soniya jimlikdan keyin `false` yuboriladi (har bosishda emas)
  - Read: chat ochilganda, yangi xabar kelganda va tab’ga qaytilganda (`visibilitychange`) `{"type":"read"}` yuboriladi
  - Xabar matni **faqat `textContent`** orqali qo‘yiladi, `innerHTML` ishlatilmaydi (XSS himoyasi)
- `ws://` yoki `wss://` sahifa protokoliga qarab avtomatik tanlanadi.

---

## 7. Xavfsizlik

| Xavf | Himoya |
|---|---|
| Login qilmagan user WS’ga ulanadi | `AuthMiddlewareStack` + `connect()`da `is_authenticated` → 4001 |
| Begona suhbatni tinglash | Guruh nomi URL’dan emas, serverda `scope["user"]` + `other_user`dan hisoblanadi. `/ws/chat/5/` ochgan user **faqat o‘zi va 5-user** suhbatiga kiradi |
| Cross-Site WebSocket Hijacking (begona sayt user cookie’si bilan ulanadi) | `AllowedHostsOriginValidator` — `Origin` header `ALLOWED_HOSTS`da bo‘lishi shart |
| XSS | JS’da `textContent`, template’da `json_script` |
| CSRF | Forma’larda `{% csrf_token %}`, `fetch`da `X-CSRFToken` header, logout faqat POST |
| Secretlar kodda | `.env` + `.gitignore` |
| Juda uzun xabar / noto‘g‘ri JSON | `services.create_message` validatsiyasi, `receive()`da `try/except` → `{"type":"error"}` |
| Production | `DEBUG=False` bo‘lsa Secure cookie, HSTS, SSL redirect avtomatik yoqiladi |

**CORS:** frontend va backend bitta domenda, shuning uchun `django-cors-headers` **kerak emas**. Agar frontend alohida domenda bo‘lsa (masalan React `localhost:3000`), `django-cors-headers` o‘rnatiladi, `CSRF_TRUSTED_ORIGINS`ga domen qo‘shiladi va WebSocket uchun `ALLOWED_HOSTS` sozlanadi.

---

## 8. Test qilish

### 8.1 Avtomatik testlar (Redis shart emas, testlar InMemory layer ishlatadi)
```bash
python manage.py test
# Ran 11 tests ... OK
```
`chat/tests/test_consumers.py`da `WebsocketCommunicator` bilan consumerni brauzersiz qanday test qilish ko‘rsatilgan.

### 8.2 Qo‘lda test (2 user)
Bitta brauzer ichida ikkita user bo‘lib bo‘lmaydi, chunki cookie umumiy. Shuning uchun:
1. **Chrome** oddiy oynada `ali` bilan ro‘yxatdan o‘ting.
2. **Chrome Incognito** (yoki Firefox) oynasida `vali` bilan ro‘yxatdan o‘ting.
3. Ali oynasida Vali yonida 🟢 paydo bo‘lishini kuzating.
4. Ali → Vali’ni tanlab yozing. Xabar Vali’da **refreshsiz** paydo bo‘ladi.
5. Vali’da hali chat ochilmagan bo‘lsa, Ali yonida **badge** (1) chiqadi.
6. Ali yozayotganda Vali’da *"Ali is typing..."* chiqadi.
7. Vali chatni ochganda Ali’dagi ✓ belgisi ko‘k ✓✓ ga aylanadi.
8. Vali oynasini yoping. Ali’da ⚫ va "last seen HH:MM" chiqadi.
9. Sahifani yangilang. Tarix DB’dan qayta yuklanadi.

### 8.3 DevTools’da kuzatish
`F12 → Network → WS` → `presence/` yoki `chat/2/` → **Messages** tab. Kelgan va ketgan JSON’lar shu yerda ko‘rinadi.

Konsoldan qo‘lda xabar yuborish:
```js
const ws = new WebSocket(`ws://${location.host}/ws/chat/2/`);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
ws.onopen = () => ws.send(JSON.stringify({type: "chat_message", message: "Konsoldan salom"}));
```

### 8.4 Redis’ni kuzatish
```bash
redis-cli monitor         # Channel Layer Redis’ga nima yozayotganini jonli ko‘rish
```
Tajriba: Redis’ni to‘xtating (`brew services stop redis`) va xabar yuboring. Xato chiqadi. Bu Channel Layer Redis’ga bog‘liqligini ko‘rsatadi.

### 8.5 Xavfsizlik tekshiruvi
- Logout qilib `/api/users/` oching → 403.
- Konsoldan `new WebSocket("ws://127.0.0.1:8000/ws/chat/99999/")` → close code 4004.

### 8.6 Server qulagandan keyin
Server to‘satdan o‘chsa, `disconnect()` chaqirilmaydi va userlar "online" bo‘lib qolishi mumkin:
```bash
python manage.py reset_presence
```

---

## 9. Loyiha qanday ishlaydi

1. User login qiladi. Django session cookie beradi.
2. Chat sahifasi ochiladi. JS `/api/users/` orqali userlar ro‘yxatini oladi va `/ws/presence/`ga ulanadi. Server `active_connections += 1` qiladi va `presence` guruhiga "online" eventini yuboradi, boshqalarda 🟢 yonadi.
3. User suhbatdoshni tanlaydi. JS HTTP orqali tarixni oladi, keyin `/ws/chat/<id>/`ga ulanadi. Consumer ikki user uchun `Conversation`ni topadi va connectionni `chat_<id>` guruhiga qo‘shadi.
4. Xabar yoziladi: `receive` → DB’ga saqlash → `group_send` → Redis → ikkala consumer → `send` → ikkala brauzer.
5. Typing va read ham xuddi shu yo‘l bilan yuradi, faqat DB’ga yozilmaydi (read esa `is_read=True` qiladi).
6. Tab yopiladi: `disconnect` → `group_discard` → `active_connections -= 1` → 0 bo‘lsa "offline" eventi.

---

## 10. Amaliy vazifalar

### Asosiy 5 ta vazifa

**1. "Load older messages" (pagination)** ⭐
API `?before=<id>` parametrini allaqachon qo‘llaydi. Chat tepasiga scroll qilinganda eski 50 ta xabarni yuklang va ro‘yxat boshiga qo‘shing. Scroll pozitsiyasi sakramasin.

**2. Xabarni o‘chirish** ⭐⭐
Faqat o‘z xabarini o‘chirish mumkin bo‘lsin: `{"type": "delete_message", "id": 5}`. Ikkala tomonda ham xabar "🚫 Bu xabar o‘chirildi" ga aylansin. `sender == self.user` tekshiruvini unutmang, aks holda begona xabarni o‘chirish mumkin bo‘ladi.

**3. Rate limiting (spam himoyasi)** ⭐⭐
Bir user 10 soniyada 10 tadan ortiq xabar yubora olmasin. Maslahat: consumer ichida vaqtlar ro‘yxatini saqlang yoki Redis’da `INCR` + `EXPIRE` ishlating. Oshib ketsa `{"type":"error"}` qaytaring.

**4. Userlar ro‘yxatida oxirgi xabar va vaqt** ⭐⭐
Sidebar’da har bir user tagida oxirgi xabar ko‘rinsin (*"Ali: Qalaysan?" · 14:32*). Ro‘yxat oxirgi faollik bo‘yicha saralansin (`Conversation.updated_at`). `Subquery`/`OuterRef` bilan N+1 muammosidan qoching.

**5. Brauzer bildirishnomasi va ovoz** ⭐
Tab faol bo‘lmaganda yangi xabar kelsa, `Notification API` orqali bildirishnoma chiqsin va sahifa sarlavhasi `(3) Private Chat` ko‘rinishiga o‘tsin.

### Qo‘shimcha (mustaqil) vazifalar
6. **Userlarni qidirish** — sidebar’ga search input qo‘shing (`/api/users/?search=ali`, DRF `SearchFilter`).
7. **Xabarni tahrirlash** — `edited_at` maydoni va "(edited)" belgisi.
8. **Rasm yuborish** — `ImageField`. Rasm HTTP orqali yuklanadi, WebSocket orqali esa faqat uning URL’i yuboriladi. Nega faylni WS orqali yubormaslik kerakligini tushuntiring.
9. **Group chat** — `Conversation`ni `participants = ManyToManyField` ga o‘zgartiring. Qaysi kod qismlari o‘zgaradi?
10. **Token bilan WebSocket auth** — frontend alohida (React/mobil) bo‘lganda cookie yo‘q. `?token=...` orqali ishlaydigan custom middleware yozing (`BaseMiddleware`). Token URL’da nega xavfli ekanini va buning muqobilini muhokama qiling.
11. **Docker Compose** — `web` (daphne) + `redis` + `postgres` servislarini bitta `docker-compose.yml`da ishga tushiring.
12. **Masshtablash tajribasi** — ikkita serverni turli portlarda ishga tushiring (`runserver 8000` va `8001`). Ali 8000’da, Vali 8001’da bo‘lsin. Chat ishlaydimi? `CHANNEL_LAYERS`ni `InMemoryChannelLayer`ga almashtirib, qayta sinab ko‘ring va farqni tushuntiring. *(Redis nima uchun kerakligining eng yaxshi isboti shu.)*
