# Market Intel — база знаний по рынку недвижимости Москвы

База ежедневно собирается из профильных Telegram-каналов и чатов через личный аккаунт Ивана (Telethon).
Используется AI-агентами для контента и быстрых ответов клиентам.

## Структура

```
.business/market-intel/
├── README.md             — этот файл (для агентов)
├── INSTALL.md            — пошаговая установка (для Ивана, однократно)
├── sources.yaml          — список каналов с категориями (генерится init.py)
├── intel.db              — SQLite БД со всеми постами + FTS5 поиск (бинарник)
├── raw/                  — сырые посты по дням (JSONL, бэкап)
│   └── 2026-05-20.jsonl
├── digest/
│   ├── daily/            — хроника по дням
│   │   └── 2026-05-20.md
│   └── topics/           — накопительные тематические файлы
│       ├── ipoteka-stavka.md
│       ├── novostroyki-launch.md
│       ├── akcii-zastroyshchikov.md
│       ├── kommerciya-bc.md
│       ├── makroekonomika.md
│       ├── analitika-rynka.md
│       └── zhk/<slug>.md     — по конкретным ЖК
├── logs/                 — логи Task Scheduler
└── scripts/
    ├── config.py         — общие константы
    ├── db.py             — SQLite + FTS5
    ├── init.py           — авторизация + чтение addlist-папок (одноразово)
    ├── parser.py         — ежедневный сбор постов
    ├── processor.py      — AI-обработка через Claude
    ├── query.py          — утилита поиска для агентов
    ├── run_daily.bat     — bat для Task Scheduler
    ├── requirements.txt
    └── dotenv.example
```

## Как агенты используют базу

### Вариант 1 — Grep по тематическим Markdown-файлам (быстрее всего)

Тематические файлы — это **главный канал** доступа. Каждая запись = факт с датой, источником и ссылкой на оригинал.

```
Grep pattern="эскроу" path=".business/market-intel/digest/topics/makroekonomika.md"
Read file=".business/market-intel/digest/topics/akcii-zastroyshchikov.md"
Read file=".business/market-intel/digest/topics/zhk/republic.md"
```

### Вариант 2 — Полнотекстовый поиск через query.py

Когда тематические файлы не покрывают запрос или нужен сырой текст постов:

```bash
python .business/market-intel/scripts/query.py --text "ключевая ставка" --days 14
python .business/market-intel/scripts/query.py --tag developer:ПИК --days 30
python .business/market-intel/scripts/query.py --tag zhk:Republic
python .business/market-intel/scripts/query.py --stats
```

### Вариант 3 — Прямой SQL (для сложных запросов)

```bash
sqlite3 .business/market-intel/intel.db "
  SELECT date, c.title, substr(p.text, 1, 200), p.url
  FROM posts p JOIN channels c ON c.id=p.channel_id
  JOIN posts_fts f ON f.rowid=p.id
  WHERE posts_fts MATCH 'рассрочка'
  ORDER BY date DESC LIMIT 20
"
```

## Когда какой инструмент

| Задача | Инструмент |
|---|---|
| «Что нового по ставке за месяц» | Grep по `topics/ipoteka-stavka.md` |
| «Какие сейчас акции у Самолёта» | `query.py --tag developer:Самолёт --days 14` |
| «Что писали про ЖК Republic» | `Read topics/zhk/republic.md` |
| «Все упоминания слова "эскроу"» | `query.py --text "эскроу" --days 60` |
| «Сводка за вчера» | `Read digest/daily/YYYY-MM-DD.md` |
| «Какие каналы парсятся» | `query.py --channels` |
| Сложная аналитика | прямой SQL по `intel.db` |

## Что делает обработка (processor.py)

Для каждого нового поста Claude Haiku извлекает:
- **relevant**: нерелевантные (реклама, оффтоп, регионы кроме Москвы) отсеиваются
- **topics**: одна или несколько тем из фиксированного списка (см. `processor.py` → `TOPICS`)
- **zhk / bc**: упомянутые ЖК и БЦ
- **developers**: застройщики (ПИК, Самолёт, MR Group, Donstroy и т.д.)
- **segment**: жильё-бизнес / жильё-премиум / коммерция / макро
- **importance**: 1–5 (для приоритизации в daily-дайджестах)
- **summary**: 1–2 предложения по делу

Результат расходится в:
1. Тематические Markdown-файлы (append с заголовком, цифрой важности, ссылкой)
2. Daily-файл текущей даты (группировка по темам внутри)
3. Теги в БД (для `query.py --tag`)

## Расписание работы

- **Ежедневно в 07:00** через Windows Task Scheduler запускается `run_daily.bat`:
  1. `parser.py` — собирает посты за последние 26 часов (с запасом)
  2. `processor.py` — обрабатывает их через Claude
- Логи: `logs/daily-YYYYMMDD.log`

## Стоимость

При ~30 каналах:
- Telegram API — бесплатно
- Claude Haiku 4.5 — ~$2–4/мес (5–15K постов × ~500 токенов)

## Что НЕ парсится

- Чисто медийные посты (фото без подписи)
- Посты короче 20 символов
- Посты, помеченные `relevant: false` процессором (реклама, оффтоп)

## Что делать, если база молчит

1. Глянуть последний лог в `logs/`
2. Запустить вручную: `cd scripts && python parser.py`
3. Если ругается на сессию — `python init.py` (заново авторизоваться)
4. Если ругается на каналы — проверить `python query.py --channels`
