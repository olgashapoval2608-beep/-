# 🚀 Як створити і розмістити бота

## Крок 1. Створи бота в Telegram (безкоштовно)

1. Відкрий у Telegram [@BotFather](https://t.me/BotFather) → `/newbot`.
2. Введи назву (наприклад, «Мій дієтолог») та username, що закінчується на `bot`.
3. BotFather надішле **токен** на кшталт `123456789:AAH...` — це `TELEGRAM_BOT_TOKEN`.
4. Необовʼязково: `/setuserpic` (аватар), `/setdescription` (опис до кнопки «Старт»).

> Токен — як пароль. Не публікуй його і не комітьте `.env` у git.

## Крок 2. Отримай ключ Claude API (платно, оплата за використання)

1. Зареєструйся на https://platform.claude.com/.
2. **Billing** → поповни баланс (передоплата, від кількох доларів).
3. **API Keys** → Create Key → скопіюй ключ `sk-ant-...` — це `ANTHROPIC_API_KEY`.
4. Раджу в **Limits** встановити місячний ліміт витрат — так точно не буде сюрпризів.

## Крок 3. Налаштуй `.env`

```bash
cp .env.example .env
```

Впиши два токени. Щоб ботом не могли користуватися сторонні люди за твій кошт:
1. Впиши в `ALLOWED_USERS` будь-яке число (наприклад, `1`) і запусти бота.
2. Напиши боту — він відповість «Це приватний бот. Твій Telegram ID: 123456789».
3. Впиши цей ID (і ID друзів через кому) в `ALLOWED_USERS` і перезапусти.

## Крок 4. Обери, де запускати

Бот працює через *polling* (сам опитує Telegram), тож йому не потрібні домен,
HTTPS чи відкриті порти — лише інтернет і комп'ютер, що працює 24/7.

### Варіант А — свій комп'ютер (безкоштовно, для тесту)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m bot.main
```

Бот працює, поки відкрите вікно терміналу і комп'ютер не спить.

### Варіант Б — VPS-сервер з Docker (рекомендую, ~4–6 $/міс або безкоштовно)

Підійде будь-який VPS з Ubuntu: Hetzner, DigitalOcean, Contabo тощо (найдешевші
тарифи — кілька доларів на місяць). Безкоштовні варіанти: Oracle Cloud «Always Free»,
Google Cloud e2-micro (free tier). Ціни й умови змінюються — перевір на сайті.

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

### Варіант Г — хмарна платформа (Railway тощо)

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
| Сервер | 0 $ (свій ПК / free tier) або ~4–6 $/міс (VPS) |
| **Claude API** | **оплата за кожен запит** |

Чому платно: розпізнавання їжі на фото робить модель Claude на серверах Anthropic,
і вони беруть оплату за обсяг тексту/зображень (токени) у кожному запиті. Бот —
наш, а «мозок» — орендований.

Орієнтовна ціна **одного аналізу фото** (грубо, залежить від фото і відповіді):

| Модель (`CLAUDE_MODEL`) | За фото | 10 фото/день протягом місяця |
|---|---|---|
| `claude-opus-5` (за замовчуванням, найточніша) | ~4–9 ¢ | ~12–27 $ |
| `claude-sonnet-5` (добрий баланс) | ~1.5–3.5 ¢ | ~5–11 $ |
| `claude-haiku-4-5` (найдешевша) | ~0.5–1.5 ¢ | ~2–5 $ |

Реальні витрати дивись у консолі platform.claude.com → Usage. Щоб економити:
- постав `CLAUDE_MODEL=claude-sonnet-5` у `.env`;
- заповни `ALLOWED_USERS`;
- зменш `DAILY_AI_LIMIT`.

Безкоштовні функції (не звертаються до ШІ): вода, вага, /today, /week, досягнення,
експорт, нагадування.
