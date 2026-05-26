# Установка парсера Telegram-каналов

Два режима установки:
- **🚀 Быстрый (автоматический):** запустить `setup.ps1` — он всё сделает сам, ваше участие ~5 минут
- **🔧 Ручной (по шагам ниже):** если что-то пошло не так, или хочется понять каждый шаг

---

## 🚀 Быстрый режим (рекомендуется)

1. Открыть проводник: `C:\Users\ivlan\OneDrive\Desktop\Вайбкодинг\.business\market-intel\`
2. Правый клик по файлу **`setup.ps1`** → **Run with PowerShell**
   - Если Windows ругается на «execution policy», открыть PowerShell (Win+X → Terminal) и выполнить один раз:
     ```powershell
     Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
     ```
3. Скрипт сам:
   - Установит Python (через winget, если нет)
   - Создаст venv и поставит зависимости
   - Откроет в браузере вкладки my.telegram.org и console.anthropic.com
   - Откроет блокнот с шаблоном `.env` — вам нужно вставить 4 значения и нажать Ctrl+S
   - Запустит первичную авторизацию в Telegram (вам придёт код-подтверждение в Telegram)
   - Заберёт первые посты и обработает через Claude
   - Зарегистрирует Task Scheduler на 07:00 каждый день
4. Готово — больше ничего делать не нужно. Завтра в 07:00 новый запуск автоматом.

**От вас требуется:**
- 1 раз — получить api_id/api_hash на my.telegram.org (5 минут)
- 1 раз — получить Anthropic API key + пополнить $5 (5 минут)
- 1 раз — ввести код подтверждения из Telegram (10 секунд)
- Если включена двухфакторка — облачный пароль (10 секунд)

---

## 🔧 Ручной режим (если что-то сломалось в авто)

Время на установку: **30–40 минут**, из них реально активных действий — минут 10.

---

## Шаг 1. Установить Python 3.11+

1. Открыть https://www.python.org/downloads/windows/
2. Скачать установщик **Python 3.12** или новее (Windows installer 64-bit)
3. Запустить установщик. **ВАЖНО:** на первом экране поставить галочку **«Add Python to PATH»** (внизу окна) → нажать «Install Now»
4. Проверить установку: открыть PowerShell (Win+X → Terminal) и выполнить:
   ```powershell
   python --version
   ```
   Должно вывести `Python 3.12.x` (или выше).

---

## Шаг 2. Получить ключи Telegram API

Это нужно один раз. Ключи привязываются к вашему номеру.

1. Открыть https://my.telegram.org/auth в браузере
2. Войти по номеру телефона (придёт код в Telegram)
3. Открыть раздел **«API development tools»**
4. Заполнить форму создания приложения:
   - App title: `market-intel` (любое имя)
   - Short name: `intel`
   - Platform: Desktop
   - Description: пусто
5. Нажать **«Create application»**
6. На открывшейся странице будут две строки:
   - **api_id**: число вида `12345678`
   - **api_hash**: строка вида `0a1b2c3d4e5f6789abcdef0123456789`

   Скопировать их — понадобятся в Шаге 4.

---

## Шаг 3. Получить ключ Anthropic API

1. Открыть https://console.anthropic.com/
2. Зарегистрироваться (или войти, если есть аккаунт)
3. Пополнить баланс **минимум на $5** (хватит на несколько месяцев — Haiku 4.5 дешёвая)
4. Перейти в **API Keys** → **Create Key**
5. Скопировать ключ (вида `sk-ant-api03-xxxx...`) — он показывается **только один раз**

---

## Шаг 4. Настроить проект

1. Открыть PowerShell в папке проекта:
   ```powershell
   cd "C:\Users\ivlan\OneDrive\Desktop\Вайбкодинг\.business\market-intel\scripts"
   ```

2. Создать виртуальное окружение Python (изоляция зависимостей):
   ```powershell
   python -m venv ..\venv
   ..\venv\Scripts\Activate.ps1
   ```
   Если PowerShell ругается на скрипты — выполнить **в админ-PowerShell** один раз:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

3. Установить зависимости:
   ```powershell
   pip install -r requirements.txt
   ```

4. Создать файл `.env` из шаблона:
   ```powershell
   copy dotenv.example .env
   notepad .env
   ```
   Заполнить значения:
   ```
   TELEGRAM_API_ID=12345678
   TELEGRAM_API_HASH=0a1b2c3d4e5f6789abcdef0123456789
   TELEGRAM_PHONE=+79991234567
   TELEGRAM_FOLDER_INVITES=https://t.me/addlist/_UqsunmXhF9hNjli,https://t.me/addlist/bb2t_WekrkQ2ODI6
   ANTHROPIC_API_KEY=sk-ant-api03-xxxx...
   ANTHROPIC_MODEL=claude-haiku-4-5-20251001
   LOOKBACK_HOURS=26
   ```
   Сохранить (Ctrl+S) и закрыть.

---

## Шаг 5. Первичная авторизация и импорт каналов

В той же PowerShell-сессии (с активированным venv):

```powershell
python init.py
```

Скрипт попросит:
1. **Код подтверждения** (придёт в Telegram от @Telegram) — ввести его
2. Если у вас включена **двухфакторка** — ввести облачный пароль Telegram

После авторизации:
- Импортируются обе addlist-папки (если их ещё нет в аккаунте)
- Все каналы из этих папок попадут в БД и в `sources.yaml`
- Появится файл `telegram.session` — не удалять, в нём токен авторизации

Проверить, что каналы подхватились:
```powershell
python query.py --channels
```

Должен вывести список всех каналов из обеих папок.

---

## Шаг 6. Первый ручной запуск парсера и обработки

```powershell
python parser.py
python processor.py
```

Первый раз парсер заберёт посты за последние 26 часов. Processor их обработает через Claude.

Проверить результат:
```powershell
python query.py --stats
```

Должно показать сколько постов в базе. Заглянуть в файлы:
- `..\digest\daily\2026-05-20.md` — дайджест за сегодня
- `..\digest\topics\*.md` — накопительные темы

---

## Шаг 7. Настроить ежедневный автозапуск (Task Scheduler)

1. Win+R → ввести `taskschd.msc` → Enter
2. В правой панели **Create Task...**
3. Вкладка **General**:
   - Name: `market-intel-daily`
   - Run only when user is logged on
4. Вкладка **Triggers** → **New...**:
   - Begin the task: On a schedule
   - Daily, время старта: например `07:00`
   - Recur every: 1 day
   - OK
5. Вкладка **Actions** → **New...**:
   - Action: Start a program
   - Program/script: `C:\Users\ivlan\OneDrive\Desktop\Вайбкодинг\.business\market-intel\scripts\run_daily.bat`
   - Start in: `C:\Users\ivlan\OneDrive\Desktop\Вайбкодинг\.business\market-intel\scripts`
   - OK
6. Вкладка **Conditions**:
   - Снять «Start the task only if the computer is on AC power» (чтобы запускался и на батарее)
7. Вкладка **Settings**:
   - Поставить «Run task as soon as possible after a scheduled start is missed» (если компьютер был выключен)
8. ОК → ввести пароль учётки Windows

**Проверить:** правый клик по задаче → **Run**. Через 2-3 минуты заглянуть в `..\logs\daily-YYYYMMDD.log` — должно быть «END» в конце.

---

## Готово

Всё работает. Каждое утро в 7:00 (или когда компьютер включится) база обновляется. Логи — в папке `logs/`.

Если что-то сломается:
- Смотреть последний лог в `logs/`
- Запустить вручную `python parser.py` и `python processor.py` — увидеть ошибку в консоли

---

## Что если каналы изменились

Если добавили **новые каналы в addlist-папки в Telegram** — нужно один раз перечитать структуру:
```powershell
..\venv\Scripts\Activate.ps1
python init.py
```
Он подхватит новые каналы и обновит `sources.yaml`. После этого парсер сам начнёт их парсить.
