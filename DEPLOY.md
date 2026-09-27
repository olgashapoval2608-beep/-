# 🚀 Як створити і розмістити бота

## Крок 1. Створи бота в Telegram (безкоштовно)

1. Відкрий у Telegram [@BotFather](https://t.me/BotFather) → `/newbot`.
2. Введи назву (наприклад, «Мій дієтолог») та username, що закінчується на `bot`.
3. BotFather надішле **токен** на кшталт `123456789:AAH...` — це `TELEGRAM_BOT_TOKEN`.
4. Необовʼязково: `/setuserpic` (аватар), `/setdescription` (опис до кнопки «Старт»).

> Токен — як пароль. Не публікуй його і не комітьте `.env` у git.

## Крок 2. Отримай безкоштовний ключ Google Gemini

1. Зайди на https://aistudio.google.com/apikey під своїм Google-акаунтом.
2. Натисни **Create API key** і скопіюй ключ — це `GEMINI_API_KEY`.
3. Банківська картка не потрібна. Поки не підключаєш білінг у Google Cloud,
   ключ працює лише на безкоштовному тарифі, і гроші списатися не можуть.

Обмеження безкоштовного тарифу (Google їх змінює, актуальні цифри — в AI Studio):
приблизно 10–15 запитів на хвилину і кілька сотень – ~1500 на день на весь бот.
Для себе, родини й друзів цього вистачає з запасом. Якщо ліміт вичерпано, бот
чемно попросить зачекати.

> Зверни увагу: на безкоштовному тарифі Google може використовувати запити
> (фото їжі та текст) для покращення своїх продуктів.

## Крок 3. Налаштуй `.env`

```bash
cp .env.example .env
```

Впиши `TELEGRAM_BOT_TOKEN` і `GEMINI_API_KEY`. Щоб сторонні люди не витрачали
твій безкоштовний ліміт запитів:
1. Впиши в `ALLOWED_USERS` будь-яке число (наприклад, `1`) і запусти бота.
2. Напиши боту — він відповість «Це приватний бот. Твій Telegram ID: 123456789».
3. Впиши цей ID (і ID друзів через кому) в `ALLOWED_USERS` і перезапусти.

## Крок 4. Обери, де запускати

Бот працює через *polling* (сам опитує Telegram), тож йому не потрібні домен,
HTTPS чи відкриті порти — лише інтернет і комп'ютер, що працює 24/7.

### Варіант А — свій комп'ютер (безкоштовно)

1. Встанови Python 3.10+ з https://www.python.org/downloads/ (на Windows постав
   галочку «Add Python to PATH»).
2. Завантаж код: на GitHub → **Code → Download ZIP** і розпакуй, або `git clone`.
3. У папці з ботом відкрий термінал і виконай:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python -m bot.main
```

Бот працює, поки відкрите вікно терміналу і комп'ютер не спить. Для себе — ідеально.

### Безкоштовний сервер 24/7

Щоб бот працював, навіть коли комп'ютер вимкнено:
- **Oracle Cloud «Always Free»** — безкоштовна віртуальна машина назавжди
  (при реєстрації просять картку для перевірки, але не списують гроші).
- **Google Cloud e2-micro** (free tier) — одна маленька машина безкоштовно.
- Старий ноутбук чи Raspberry Pi вдома теж підійде.

Умови безкоштовних тарифів змінюються — перевір на сайті перед реєстрацією.
Після створення сервера з Ubuntu дій за варіантом Б або В нижче.

### Варіант Б — сервер з Docker

Підійде безкоштовний сервер вище або платний VPS (Hetzner, DigitalOcean тощо,
від кількох доларів на місяць).

```bash
# 1. Підключись до сервера
ssh root@IP_СЕРВЕРА

# 2. Встанови Docker
curl -fsSL https://get.docker.com | sh

# 3. Завантаж код
git clone https://github.com/olgashapoval2608-beep/-.git calorie-bot
cd calorie-bot

# 4. Створи .env і впиши токени
cp .env.example .env
nano .env        # Ctrl+O, Enter — зберегти; Ctrl+X — вийти

# 5. Запусти (бот сам перезапуститься після збою чи перезавантаження сервера)
docker compose up -d --build

# Логи:
docker compose logs -f
```

База даних зберігається в папці `data/` на сервері й переживає перезапуски.

**Оновити бота** після змін у коді:

```bash
cd calorie-bot && git pull && docker compose up -d --build
```

**Резервна копія** даних: просто скопіюй файл `data/bot.db`.

### Варіант В — VPS без Docker (systemd)

```bash
sudo apt update && sudo apt install -y python3-venv git
sudo adduser --disabled-password bot && sudo -iu bot
git clone https://github.com/olgashapoval2608-beep/-.git calorie-bot && cd calorie-bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env
exit
sudo cp /home/bot/calorie-bot/deploy/calorie-bot.service /etc/systemd/system/
sudo systemctl enable --now calorie-bot
journalctl -u calorie-bot -f      # логи
```

### Варіант Г — хмарна платформа (Railway тощо, платно)

Можна розгорнути з GitHub на Railway: New Project → Deploy from GitHub →
вибрати репозиторій (він підхопить `Dockerfile`) → додати змінні з `.env` у
Variables → додати **Volume** з шляхом `/app/data`, інакше база зникатиме при кожному
деплої. Платно, від ~5 $/міс. Безкоштовні тарифи, які «засинають»
(наприклад, Render free web service), для такого бота не підходять.

## 💰 Скільки це коштує

| Що | Ціна |
|---|---|
| Telegram-бот | безкоштовно |
| Код | безкоштовно (він твій) |
| ШІ — Google Gemini (за замовчуванням) | **безкоштовно** в межах лімітів |
| Сервер | безкоштовно (свій ПК / Oracle / Google free tier) |

**Разом: 0 грн.**

### Хочеш точніше розпізнавання? (необовʼязково, платно)

Бот вміє працювати і з Claude від Anthropic — це потужніші моделі для розпізнавання,
але безкоштовного тарифу в нього немає: оплата за кожен запит (передоплата на
https://platform.claude.com/). Орієнтовно за одне фото (грубо):

| `CLAUDE_MODEL` | За фото |
|---|---|
| `claude-opus-5` | ~4–9 ¢ |
| `claude-sonnet-5` | ~1.5–3.5 ¢ |
| `claude-haiku-4-5` | ~0.5–1.5 ¢ |

Щоб увімкнути: у `.env` постав `AI_PROVIDER=claude` і впиши `ANTHROPIC_API_KEY`.
