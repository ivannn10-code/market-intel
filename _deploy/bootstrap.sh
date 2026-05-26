#!/bin/bash
# ============================================================
#  bootstrap.sh — установка market-intel на Ubuntu сервер
#  Запускать ОДИН раз из root:
#    bash <(curl -fsSL https://raw.githubusercontent.com/ivannn10-code/market-intel/main/_deploy/bootstrap.sh)
#
#  Или: git clone ... && cd market-intel && bash _deploy/bootstrap.sh
# ============================================================

set -e

INSTALL_DIR="/opt/apps/market-intel"
REPO_URL="https://github.com/ivannn10-code/market-intel.git"
SERVICE_USER="root"

echo "============================================"
echo "  market-intel — установка на сервер"
echo "============================================"
echo ""

# 1. Установка системных зависимостей
echo "[1/7] apt update + install Python venv, git, sqlite, curl..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    git sqlite3 curl ca-certificates tzdata \
    2>&1 | tail -3

# 2. Часовой пояс — Moscow
echo "[2/7] Часовой пояс MSK..."
timedatectl set-timezone Europe/Moscow 2>/dev/null || true
date

# 3. Клон или обновление репо
echo "[3/7] Клонирую/обновляю репо..."
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git fetch --all -q
    git reset --hard origin/main -q
    echo "  ✓ обновлено: $(git rev-parse --short HEAD)"
else
    rm -rf "$INSTALL_DIR"
    mkdir -p /opt/apps
    git clone -q "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    echo "  ✓ склонировано: $(git rev-parse --short HEAD)"
fi

# 4. Создание venv и установка Python-зависимостей
echo "[4/7] venv + pip install..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/scripts/requirements.txt"
echo "  ✓ зависимости установлены"

# 5. Проверка .env
echo "[5/7] Проверка .env..."
ENV_FILE="$INSTALL_DIR/scripts/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "  ⚠ .env не найден — нужно создать руками:"
    echo "    cp $INSTALL_DIR/scripts/dotenv.example $ENV_FILE"
    echo "    nano $ENV_FILE"
    echo "    (заполни TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,"
    echo "     ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_CHAT_ID)"
    echo ""
    echo "  ✗ Прерываю — после создания .env запусти этот скрипт снова."
    exit 1
fi
echo "  ✓ .env существует"

# 6. systemd unit для бота
echo "[6/7] systemd unit market-intel-bot.service..."
cat > /etc/systemd/system/market-intel-bot.service <<EOF
[Unit]
Description=market-intel Telegram Bot Server (long polling)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/scripts
Environment="PYTHONIOENCODING=utf-8"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$INSTALL_DIR/venv/bin/python -u bot_server.py
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/logs/bot.log
StandardError=append:$INSTALL_DIR/logs/bot.err.log

# Лимиты ресурсов
MemoryMax=300M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF

mkdir -p "$INSTALL_DIR/logs"

systemctl daemon-reload
systemctl enable market-intel-bot.service 2>&1 | tail -1
echo "  ✓ unit зарегистрирован"

# 7. cron для daily/weekly
echo "[7/7] cron jobs..."
CRON_FILE=/etc/cron.d/market-intel
cat > "$CRON_FILE" <<EOF
# market-intel daily + weekly
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
PYTHONIOENCODING=utf-8
PYTHONUNBUFFERED=1

# Ежедневно 7:00 МСК — parser → processor → notifier → daily_digest
0 7 * * * root $INSTALL_DIR/_deploy/run_daily.sh >> $INSTALL_DIR/logs/cron-daily.log 2>&1

# По понедельникам 9:00 МСК — weekly_digest
0 9 * * 1 root $INSTALL_DIR/venv/bin/python -u $INSTALL_DIR/scripts/weekly_digest.py --send >> $INSTALL_DIR/logs/cron-weekly.log 2>&1
EOF
chmod 644 "$CRON_FILE"
echo "  ✓ cron установлен"

echo ""
echo "============================================"
echo "  ✓ ВСЁ ГОТОВО"
echo "============================================"
echo ""
echo "Следующие шаги:"
echo "  1. Проверь .env (если ещё не сделал)"
echo "  2. Один раз авторизуй Telegram userbot:"
echo "     cd $INSTALL_DIR/scripts && ../venv/bin/python init.py"
echo "     (введёшь код подтверждения из Telegram)"
echo "  3. Запусти бот: systemctl start market-intel-bot"
echo "  4. Проверь логи: tail -f $INSTALL_DIR/logs/bot.log"
echo ""
