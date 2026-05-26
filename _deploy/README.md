# market-intel server deployment

Структура для развёртывания market-intel на Ubuntu 22.04 сервере.

## Что устанавливается

1. **scripts/** — весь Python-код (parser, processor, notifier, daily_digest, weekly_digest, sentiment, analytics, bot_server)
2. **venv/** — виртуальное окружение Python с зависимостями
3. **scripts/.env** — секреты (создаётся руками из dotenv.example)
4. **systemd unit** `market-intel-bot.service` — постоянный bot_server (long polling)
5. **cron** — ежедневно в 7:00 МСК daily-цепочка, по ПН в 9:00 weekly_digest

## Установка (на сервере, под root)

```bash
git clone https://github.com/ivannn10-code/market-intel.git /opt/apps/market-intel
cd /opt/apps/market-intel
bash _deploy/bootstrap.sh
```

После — заполнить `.env`:

```bash
cd /opt/apps/market-intel/scripts
cp dotenv.example .env
nano .env
```

Авторизация Telegram userbot (один раз):

```bash
cd /opt/apps/market-intel/scripts
../venv/bin/python init.py
# Введёшь код подтверждения от Telegram
```

Запуск бота:

```bash
systemctl start market-intel-bot
systemctl status market-intel-bot
journalctl -u market-intel-bot -f
```

## Управление

```bash
# Перезапуск бота
systemctl restart market-intel-bot

# Логи
tail -f /opt/apps/market-intel/logs/bot.log
tail -f /opt/apps/market-intel/logs/cron-daily.log
tail -f /opt/apps/market-intel/logs/cron-weekly.log

# Запустить daily вручную (для теста)
bash /opt/apps/market-intel/_deploy/run_daily.sh

# Обновить код из GitHub
cd /opt/apps/market-intel
git pull
systemctl restart market-intel-bot
```

## Синхронизация с локалкой Ивана

Каждое утро run_daily.sh после успешного прогона коммитит изменённые файлы из `digest/` и пушит в GitHub. На локалке Ивана `git pull` подтянет:

- `digest/daily/YYYY-MM-DD.md` — хроника дня
- `digest/topics/*.md` — накопительные темы

`intel.db` НЕ синхронизируется (бинарник + большой). Запросы агентов идут через `scripts/query.py` на сервере по SSH, либо через бота (Аналитика).

## Использование RAM

Сервер: 1 ГБ всего, ~720 МБ свободно после ОС.

| Процесс | RAM |
|---|---|
| bot_server (постоянный) | ~80 МБ |
| daily pipeline (пик при processor с Sonnet) | ~200 МБ |
| Запас | ~440 МБ |

Карусели с Chromium-рендером в 1 ГБ НЕ влезут — оставляем локально.
