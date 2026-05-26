#!/bin/bash
# Ежедневный конвейер market-intel на сервере (вызывается из cron в 7:00 МСК).

set -e

INSTALL_DIR="/opt/apps/market-intel"
cd "$INSTALL_DIR/scripts"

export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
PY="$INSTALL_DIR/venv/bin/python"

echo "=== $(date) START ==="

echo "--- [1/4] parser ---"
$PY -u parser.py || echo "PARSER FAILED, continuing"

echo "--- [2/4] processor ---"
$PY -u processor.py || echo "PROCESSOR FAILED, continuing"

echo "--- [3/4] notifier ---"
$PY -u notifier.py || echo "NOTIFIER FAILED, continuing"

echo "--- [4/4] daily_digest ---"
$PY -u daily_digest.py || echo "DIGEST FAILED"

# git push на свежие изменения в digest/ (для локальной синхронизации)
cd "$INSTALL_DIR"
if [ -n "$(git status --porcelain digest/)" ]; then
    git add digest/
    git -c user.email='market-intel@server' -c user.name='market-intel-server' \
        commit -q -m "auto: digest update $(date -u +%Y-%m-%d)" || true
    git push -q origin main 2>&1 | tail -3 || echo "git push failed (continuing)"
fi

echo "=== $(date) END ==="
