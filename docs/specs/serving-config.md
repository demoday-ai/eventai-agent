# Serving & Config - Спецификация

Запуск, конфигурация, инфраструктура, зависимости.

Код: `backend/app/config.py`, `backend/app/bot/app.py`, `backend/app/worker/celery_app.py`, `backend/app/main.py`.

---

## Режимы запуска

| Режим | Параметр | Описание |
|-------|---------|----------|
| Polling | `bot_mode=polling` | Dev-режим. Бот опрашивает Telegram API |
| Webhook | `bot_mode=webhook` | Production. Telegram отправляет updates на webhook URL через Traefik |

Webhook URL задается через `webhook_url` (например, `https://evt-ai.ru`).

---

## Environment variables

### Обязательные

| Переменная | Тип | Описание | Пример |
|-----------|-----|----------|--------|
| `database_url` | str | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/db` |
| `bot_token` | str | Telegram Bot API token | `123456:ABC-DEF...` |
| `openrouter_api_key` | str | Основной API-ключ OpenRouter | `sk-or-v1-...` |

### Опциональные

| Переменная | Тип | Default | Описание |
|-----------|-----|---------|----------|
| `bot_mode` | str | `polling` | Режим работы бота |
| `openrouter_api_keys` | str | `""` | Comma-separated список ключей для ротации |
| `openrouter_base_url` | str | `https://openrouter.ai/api/v1` | Base URL OpenRouter API |
| `openrouter_model` | str | `openai/gpt-5.1` | Модель по умолчанию |
| `qdrant_url` | str | `http://localhost:6333` | URL Qdrant vector DB |
| `embedding_model` | str | `google/gemini-embedding-001` | Модель для эмбеддингов |
| `embedding_dimensions` | int | `768` | Размерность эмбеддингов |
| `rabbitmq_url` | str | `amqp://demoday:demoday@localhost:5672//` | RabbitMQ broker URL |
| `redis_url` | str | `redis://localhost:6379/0` | Redis result backend |
| `team_chat_id` | str | `""` | Telegram chat ID для уведомлений |
| `team_bot_token` | str | `""` | Отдельный бот для уведомлений |
| `webhook_url` | str | `""` | URL для webhook mode |
| `secret_key` | str | `dev-secret-key` | Секретный ключ приложения |
| `organizer_telegram_ids` | str | `""` | Comma-separated Telegram IDs организаторов |
| `organizer_telegram_usernames` | str | `""` | Comma-separated usernames организаторов |

### Property-методы конфигурации

```python
settings.api_keys       # list[str] - объединяет openrouter_api_keys + openrouter_api_key
settings.organizer_ids  # set[str] - из organizer_telegram_ids
settings.is_organizer() # bool - проверка по ID или username
```

---

## Управление секретами

### Хранение

- Environment variables (`.env` файл, не в git)
- Pydantic BaseSettings: `model_config = {"env_file": ".env", "extra": "ignore"}`

### API keys

- Приоритет: DB (LlmApiKey table) > env (openrouter_api_keys) > env (openrouter_api_key)
- Ротация: `KeyManager` с round-robin и cooldown 60s
- DB-ключи загружаются при старте worker и бота (`worker_process_init`)
- Ключи можно добавлять/отключать через admin API без перезапуска

### Ротация через DB

Таблица `LlmApiKey`:
- `api_key` - ключ
- `key_suffix` - последние 8 символов (для логирования)
- `is_active` - флаг активности
- `last_success_at` - последний успех (синхронизируется из memory)

---

## Версии моделей

| Назначение | Модель | Провайдер |
|-----------|--------|-----------|
| Primary (chat, tools, summaries) | `openai/gpt-5.1` | OpenRouter |
| Fallback | `openai/gpt-4o-mini` | OpenRouter |
| Embedding | `google/gemini-embedding-001` | OpenRouter |

### Переключение модели

1. Active model хранится в `AppSettings` таблице (key = "llm_model")
2. Загружается в memory при старте worker и бота
3. Изменяется через admin API `PATCH /llm/model`
4. In-memory переменная `_active_model` обновляется без перезапуска
5. `get_active_model()` -> `_active_model or settings.openrouter_model`

Никогда не читает DB во время LLM-вызовов (избежание deadlock в forked Celery workers).

---

## Инфраструктура

### Сервер

- Yandex Cloud VM: 2 vCPU, 4 GB RAM, 30 GB SSD
- Домен: `evt-ai.ru`
- OS: Linux

### Docker containers

| Контейнер | Образ | Порт |
|-----------|-------|------|
| FastAPI | Custom | 8000 |
| Telegram Bot | Custom | - |
| Celery Worker | Custom | - |
| PostgreSQL | postgres:16 | 5432 |
| Qdrant | qdrant/qdrant | 6333 |
| Redis | redis:7 | 6379 |
| RabbitMQ | rabbitmq:management | 5672, 15672 |
| Flower | mher/flower | 5555 |
| Traefik | traefik:v3 | 80, 443 |

### Traefik

Reverse proxy с автоматическими SSL-сертификатами. Маршрутизация:
- `evt-ai.ru/` -> Web Admin (React)
- `evt-ai.ru/api/` -> FastAPI
- `evt-ai.ru/rabbitmq/` -> RabbitMQ Management
- `evt-ai.ru/flower/` -> Flower UI
- Webhook endpoint для Telegram Bot

---

## Worker config (Celery)

```python
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Moscow",
    task_track_started=True,
    task_time_limit=300,           # 5 min hard limit
    task_soft_time_limit=240,      # 4 min soft limit
    worker_prefetch_multiplier=1,  # Fair scheduling
    task_default_queue="default",
    task_routes={
        "cluster_projects_task": {"queue": "heavy"},
        "run_matching_task": {"queue": "heavy"},
    },
)
```

### Очереди

| Очередь | Задачи | Характеристика |
|---------|--------|---------------|
| `default` | chat_for_profile, agent_chat, generate_recommendations, generate_qa_questions, generate_comparison_matrix, embed_projects | Быстрые (< 30s) |
| `heavy` | cluster_projects, run_matching | Тяжелые (10-60s) |

### Celery task retry policy

| Задача | max_retries | Backoff |
|--------|------------|---------|
| chat_for_profile_task | 3 | `2^retries` seconds |
| extract_interests_from_text_task | 3 | `2^retries` seconds |
| embed_projects_task | 2 | `5 * (retries + 1)` seconds |
| generate_recommendations_task | 2 | `5 * (retries + 1)` seconds |
| generate_qa_questions_task | 3 | `2^retries` seconds |
| generate_comparison_matrix_task | 2 | `2^retries` seconds |
| agent_chat_task | 3 | `2^retries` seconds |

### Worker init/shutdown

```python
@worker_process_init.connect
def _init_db_engine():
    init_db_engine()          # Создание SQLAlchemy engine
    _load_config()            # Загрузка LLM model + API keys из DB

@worker_process_shutdown.connect
def _shutdown_db_engine():
    shutdown_db_engine()      # Dispose engine
```

---

## Rate limiting

**Не реализовано.** Governance risk #9 - возможно злоупотребление ботом.

Текущее состояние: любой пользователь может отправлять неограниченное количество сообщений. LLM-вызовы ограничены только квотой OpenRouter API key.

Планируется: ограничение на количество LLM-запросов в минуту / на пользователя.

---

## Зависимости

### Python packages

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| Python | 3.12+ | Runtime |
| FastAPI | latest | REST API |
| python-telegram-bot | 21.x | Telegram Bot |
| SQLAlchemy | 2.0+ | ORM (async, asyncpg) |
| Celery | latest | Task queue |
| httpx | latest | HTTP client (LLM API) |
| qdrant-client | latest | Vector DB client |
| pydantic-settings | latest | Configuration |
| redis | latest | Celery result backend |

### Внешние сервисы

| Сервис | Назначение | SLA |
|--------|-----------|-----|
| OpenRouter API | LLM inference + embeddings | Зависит от upstream (OpenAI, Google) |
| Telegram Bot API | Messaging | 99.9% |
| Yandex Cloud | Hosting | 99.95% (SLA) |
