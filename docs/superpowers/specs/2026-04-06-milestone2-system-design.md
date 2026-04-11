# Design Spec: Milestone 2 - System Design

## Контекст

Milestone 2 бонус-трека "LLM & Agentic AI" (ИТМО). Нужно зафиксировать архитектуру PoC-системы перед разработкой. Трек - агентский: фокус на взаимодействие с LLM, качество и контроль, защиты и фолбэки.

Код агента уже реализован в [demoday-ai/demoday-core](https://github.com/demoday-ai/demoday-core). System design документирует планируемую архитектуру, опираясь на существующий код.

## Решения

### Scope

- Документируем **только агентскую часть** (scope бонус-трека)
- Админка, фронтенд, инфраструктура - внешние зависимости на C4 Context
- Планируемые модули (artifact parser, expert bot flow) включены как planned

### Что реализовано vs планируется

| Компонент | Статус |
|-----------|--------|
| Профилирование (LLM-диалог, 2 уточняющих вопроса) | Реализовано |
| Retrieval pipeline (embed -> Qdrant top-30 -> rerank -> LLM-резюме) | Реализовано |
| Agent mode с 7 инструментами (tool calling) | Реализовано |
| LLM Client с ротацией ключей и fallback-моделью | Реализовано |
| Degradation (LLM недоступен -> tag overlap, timeout -> retry) | Реализовано |
| Канал бот-админка (support chat) | Реализовано |
| Парсинг артефактов (PPTX/PDF/GitHub) | **Планируется** |
| Эксперты в боте (слоты, оценки) | **Планируется** (модели и API есть, бот-хендлеры нет) |
| ask_organizer (вопрос организатору через агента) | **Планируется** (support chat есть, но не как agent tool) |
| Rate limiting | **Не реализовано** (governance risk #9) |
| PII-фильтрация | **Частично** (ФИО/username не отправляются в LLM by design, автофильтра нет) |

### Observability (текущее состояние)

- Python logging (plain text, INFO level)
- Health-эндпоинты (/health, /monitoring/llm/health, /monitoring/llm/stats)
- Flower для Celery
- Audit trail в БД (AdminAuditLog)
- Токены логируются но не сохраняются в БД
- Нет: structured logging, Sentry, Prometheus, трейсинг, cost tracking

### Формат

- Диаграммы: **Mermaid** в .md файлах (рендерится на GitHub)

## Структура артефактов

```
docs/
  system-design.md
  diagrams/
    c4-context.md
    c4-container.md
    c4-component.md
    workflow.md
    data-flow.md
  specs/
    retriever.md
    tools.md
    memory-context.md
    agent-orchestrator.md
    serving-config.md
    observability-evals.md
```

### system-design.md

Обзорный архитектурный документ:
- Ключевые архитектурные решения (ConversationHandler как state machine, Celery для async LLM, OpenRouter с key rotation)
- Список модулей и их роли (6 модулей: Profiler, Retriever, Agent/Orchestrator, Tools, ArtifactParser, ExpertFlow)
- Основной workflow выполнения запроса
- State / memory / context handling (PicklePersistence, user_data dict, chat_history до 20 сообщений, GuestProfile в БД)
- Retrieval-контур (embedding -> Qdrant -> schedule rerank -> LLM summaries)
- Tool/API-интеграции (7 инструментов + fallback)
- Failure modes, fallback, guardrails
- Технические и операционные ограничения (latency, cost, reliability)

### diagrams/

5 Mermaid-диаграмм:
- **C4 Context** - агент, пользователи (гость, эксперт, бизнес), внешние сервисы (OpenRouter, Qdrant, PostgreSQL, Telegram API, GitHub API)
- **C4 Container** - Telegram Bot (PTB), FastAPI, Celery Worker, PostgreSQL, Qdrant, Redis, RabbitMQ, Web Admin (external)
- **C4 Component** - внутреннее устройство бота: ConversationHandler, states, Profiler, AgentMode, ToolDispatcher, SupportChat
- **Workflow** - /start -> role -> profiling -> recommendations -> agent mode; с ветками ошибок (LLM timeout, Qdrant unavailable, tool failure)
- **Data flow** - данные от пользователя через систему: что отправляется в LLM, что хранится в БД, что логируется

### specs/

6 технических спецификаций:

- **retriever.md** - Gemini embedding (768d), Qdrant cosine similarity, top-30, schedule_rerank (room_bonus +3.0, conflict_penalty `-2.0 * (room_count - 1)`), fallback на tag overlap, padding до 10 результатов
- **tools.md** - 7 инструментов: контракты (входы/выходы), таймауты (compare: 25s, Q&A: 20s), side effects, валидация аргументов, белый список, роль-зависимые инструменты (get_followup vs get_pipeline)
- **memory-context.md** - PicklePersistence, user_data keys, chat_history (max 20), context budget для LLM, восстановление из БД по /start
- **agent-orchestrator.md** - ConversationHandler с 7 состояниями, правила переходов, agent_chat_task через Celery, stop conditions, retry (3 attempts, exponential backoff), fallback model (gpt-4o-mini)
- **serving-config.md** - запуск (polling/webhook), env vars, секреты (OpenRouter keys, bot token), версии моделей (gpt-5.1 primary), инфраструктура (Yandex Cloud), rate limiting (planned)
- **observability-evals.md** - текущее логирование, LLM metrics (tokens logged), offline evals (NDCG@15, Precision@15, Recall@15), планируемое (structured logging, cost tracking, Sentry), PII handling

## Акцент агентского трека

system-design.md и specs должны детально раскрывать:
- **LLM quality control**: промпт-инженерия, few-shot examples, JSON mode, валидация выхода
- **Protection mechanisms**: белый список инструментов, валидация аргументов, артефакты как user message (не system), изоляция контекстов
- **Fallback chain**: primary model -> fallback model -> no-LLM degradation (tag overlap)
- **Guardrails**: ограничение длины входа, max 20 сообщений в истории, таймауты на каждую операцию

## Источники данных

Вся информация берется из:
1. Существующий код demoday-core (фактическая архитектура)
2. docs/product-proposal.md (метрики, сценарии, ограничения)
3. docs/governance.md (риски, защита, персональные данные)
4. Планируемые модули (artifact parser, expert bot flow) - из product-proposal
