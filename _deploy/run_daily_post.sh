#!/bin/bash
# Ежедневная генерация + отправка поста в @IGDeveloper_bot.
# Cron: 08:00 МСК каждый день.
#
# Логика:
# 1. Generator создаёт пост по рубрике дня недели (если файл ещё не существует — иначе skip).
# 2. Для четверга — дополнительно lot_commercial.
# 3. Для субботы — дополнительно lot_residential.
# 4. Dispatcher отправляет ВСЕ файлы драфтов на сегодняшнюю дату.

set -e
DIR=/opt/apps/market-intel
PY=$DIR/venv/bin/python
TODAY=$(date +%Y-%m-%d)
DOW=$(date +%u)  # 1=Mon, 2=Tue, ..., 7=Sun

cd $DIR/content_engine

echo "=== $(date) START run_daily_post ($TODAY, DOW=$DOW) ==="

# 1. Основная рубрика по дню недели
echo "--- gen основной ---"
$PY -u daily_post_generator.py --date $TODAY || echo "WARN: основной generator failed, continuing"

# 2. Двойные дни — лоты
if [ "$DOW" = "4" ]; then
    echo "--- gen lot_commercial (чт) ---"
    $PY -u daily_post_generator.py --date $TODAY --rubric lot_commercial || echo "WARN: lot_commercial failed"
elif [ "$DOW" = "6" ]; then
    echo "--- gen lot_residential (сб) ---"
    $PY -u daily_post_generator.py --date $TODAY --rubric lot_residential || echo "WARN: lot_residential failed"
fi

# 3. Отправка всех готовых драфтов на сегодня
echo "--- dispatcher ---"
$PY -u daily_dispatcher.py

echo "=== $(date) END ==="
