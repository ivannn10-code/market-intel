# Навигация по market-intel

Эта папка — база знаний по рынку недвижимости Москвы, собираемая ежедневно из Telegram-каналов.

## Главное для агентов

- **[README.md](README.md)** — как пользоваться (с примерами Grep / query.py / SQL)
- **[INSTALL.md](INSTALL.md)** — установка (для Ивана однократно)

## Темы (накопительные)

- [Ипотека и ставка ЦБ](digest/topics/ipoteka-stavka.md)
- [Старты продаж и новые корпуса](digest/topics/novostroyki-launch.md)
- [Акции застройщиков](digest/topics/akcii-zastroyshchikov.md)
- [Коммерция: БЦ класса А](digest/topics/kommerciya-bc.md)
- [Макро, эскроу, ДДУ, налоги](digest/topics/makroekonomika.md)
- [Аналитика рынка](digest/topics/analitika-rynka.md)
- [ЖК — папка с файлами по каждому ЖК](digest/topics/zhk/)

> Файлы тем создаются автоматически при первой релевантной записи.

## Daily-хроника

- [digest/daily/](digest/daily/) — по одному файлу на дату

## Сырые данные

- `intel.db` — SQLite (бинарник), используется через `scripts/query.py` или `sqlite3` CLI
- `raw/YYYY-MM-DD.jsonl` — сырая выгрузка постов за день (бэкап)
- `sources.yaml` — список каналов (генерится init.py из Telegram-папок)

## Быстрые команды

```bash
# Список каналов в базе
python .business/market-intel/scripts/query.py --channels

# Статистика
python .business/market-intel/scripts/query.py --stats

# Полнотекстовый поиск
python .business/market-intel/scripts/query.py --text "ставка ЦБ" --days 30

# Поиск по тегу
python .business/market-intel/scripts/query.py --tag developer:ПИК --days 14
```
