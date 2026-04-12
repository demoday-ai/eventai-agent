# EventAI Agent - AI-куратор Demo Day

Telegram-бот с AI-агентом для навигации по Demo Day AI Talent Hub (ИТМО). Профилирование через диалог, персональные рекомендации проектов, анализ GitHub-репозиториев, инструменты агента.

## Задача

Demo Day AI Talent Hub (ИТМО) - 330 проектов, 10 залов, 2 дня. Проблемы:

- Гость видит ~16% программы и выбирает вслепую
- Эксперты приходят без информации, оценки собираются в таблицах
- Вопросы участников летят в личку организатору

## Что делает агент

- **Профилирование:** LLM уточняет роль/интересы/цели за 2-3 реплики, force extraction на 3-м ходу
- **Рекомендации:** embedding (Gemini 3072d) -> pgvector cosine search -> schedule-aware rerank -> персональная программа с расписанием по залам
- **8 инструментов агента:**
  - `show_project` - карточка проекта с данными из артефактов (PPTX/PDF/README)
  - `show_profile` - текущий профиль гостя
  - `compare_projects` - LLM-матрица сравнения 2-5 проектов
  - `generate_questions` - персонализированные Q&A вопросы для автора
  - `filter_projects` - фильтрация по тегу или технологии
  - `get_summary` - follow-up пакет (контакты + шаблон) или бизнес-пайплайн
  - `update_status` - статус проекта в бизнес-пайплайне
  - `github_drilldown` - анализ GitHub-репо: метрики, файлы, структура, коммиты, контрибьюторы (live через gh CLI)
- **GitHub анализ:** cross-reference кода с описанием проекта, health score, red flags, drill-down в любой файл
- **Артефакты:** парсинг PPTX (python-pptx), PDF (pymupdf), GitHub README -> LLM structured extraction
- **Эксперты:** оценки проектов 1-5 по критериям мероприятия
- **PDF экспорт:** программа в PDF с контактами авторов (fpdf2 + DejaVu)
- **Поддержка:** пересылка вопросов организатору с tracking ID
- **Деградация:** LLM недоступна -> tag overlap scoring, timeout -> fallback

## Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/demoday-ai/eventai-agent.git
cd eventai-agent

# 2. Настроить
cp .env.example .env
# Заполнить BOT_TOKEN и OPENROUTER_API_KEY

# 3. Запустить (postgres + redis + bot, auto-seed на первом запуске)
docker compose up -d

# Бот доступен в Telegram по ссылке из @BotFather
```

## Архитектура

```
Telegram -> aiogram 3.x (FSM 8 states, 4 middleware)
              |
              v
         PydanticAI Agent (single-turn, 8 tools)
              |
              +-> PostgreSQL + pgvector (13 tables, cosine search 3072d)
              +-> Redis (FSM state, rate limiting, per-user mutex)
              +-> OpenRouter API (DeepSeek V3.2 chat, Gemini embedding)
              +-> gh CLI (GitHub REST API, live repo analysis)
              +-> telegramify-markdown (LLM output -> Telegram entities)
```

## Стек

- Python 3.12, aiogram 3.x, PydanticAI
- SQLAlchemy 2.0 (asyncpg), pgvector (3072d Gemini embeddings)
- Redis 7, Docker Compose
- DeepSeek V3.2 (LLM), google/gemini-embedding-001 (embeddings)
- gh CLI (GitHub analysis), fpdf2 (PDF), telegramify-markdown
- python-pptx, pymupdf (artifact parsing)

## Тесты

```bash
# 202 теста
BOT_TOKEN=test python3.12 -m pytest tests/ --tb=short -q

# Coverage
BOT_TOKEN=test python3.12 -m pytest tests/ --cov=src --cov-report=term-missing

# Интерактивный CLI
OPENROUTER_API_KEY=<key> python3.12 scripts/cli_bot.py

# Stateful chat для автоматизированного тестирования (изолированные сессии)
OPENROUTER_API_KEY=<key> python3.12 scripts/chat.py --session=<name> "<сообщение>"
```

## Структура

```
src/
  main.py              # entrypoint, auto-seed, auto-embed, health :8080
  core/                # config, database, sanitize, telegram_format
  models/              # SQLAlchemy (13 tables, pgvector)
  schemas/             # Pydantic (ComparisonMatrix, ProjectExtraction)
  bot/
    states.py          # 8 FSM states
    routers/           # start, profiling, program, detail, expert, support, fallback
    middlewares/       # db, platform, throttle, reconcile
    keyboards/         # roles, program, expert
  agent/               # PydanticAI (agent.py, tools.py - 8 tools)
  services/            # platform_client, retriever, profiling, expert, support,
                       # github_analyzer, artifact_parser, pdf_export
  prompts/             # agent, profiling, qa
scripts/
  schema.sql           # DDL (13 tables, pgvector, indexes)
  seed.sql             # demo data (7 projects, 3 rooms, 7 slots)
  cli_bot.py           # interactive CLI (human testing)
  chat.py              # stateful chat (agent testing, isolated sessions)
  parse_artifacts.py   # batch PPTX/PDF/README parsing
tests/                 # 202 tests
```

## Документация

- [Product Proposal](docs/product-proposal.md) - обоснование, метрики, сценарии
- [System Design](docs/system-design.md) - архитектура, workflow, failure modes
- [Governance](docs/governance.md) - риски, PII, injection protection
- [Agent Service Spec](docs/superpowers/specs/2026-04-11-eventai-agent-service-design.md) - детальная спецификация
- [Diagrams](docs/diagrams/) - C4 Context/Container/Component, Data Flow

## За рамками PoC

- Интеграция с llm-agent-platform (LLM proxy, мониторинг, guardrails)
- Интеграция с eventai-platform (общая БД, удаление встроенного бота)
- Организация встреч 1:1 (только запрос контакта автора)
- Загрузка артефактов студентами через бота
- Локальная LLM
