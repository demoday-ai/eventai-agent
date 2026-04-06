# Observability & Evals - Спецификация

Логирование, метрики, health-эндпоинты, offline-оценки, PII handling.

Код: `backend/app/main.py`, `backend/app/api/monitoring.py`, `backend/app/services/core/llm_client.py`.

---

## Текущее логирование

### Формат

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
)
```

- Plain text, не structured
- Уровень: INFO (по умолчанию)
- 44 файла используют `logging.getLogger(__name__)`
- Вывод: stdout (Docker logs)

### Что логируется

| Модуль | Уровень | Содержимое |
|--------|---------|-----------|
| llm_client | INFO | `model, tokens_in, tokens_out, len(content), key[-8:]` |
| llm_client | WARNING | `attempt N/3 failed: HTTP {status}, key=...{8}, body={500 chars}` |
| llm_client | WARNING | `API key marked failed: ...{8} (fail_count=N)` |
| llm_client | WARNING | `All keys in cooldown, using oldest failed` |
| llm_client | INFO | `Switching to fallback model: openai/gpt-4o-mini` |
| embedding_service | INFO | `Embedded N projects for event {id}` |
| embedding_service | INFO | `Qdrant client initialized: {url}` |
| profiling_service | INFO | `Profile agent: extracted profile interests=[...]` |
| profiling_service | INFO | `Recommendations generated: N projects in X.Xs` |
| profiling_service | WARNING | `Profile embedding failed, falling back` |
| profiling_service | WARNING | `LLM summary generation failed (graceful degradation)` |
| start.py | INFO | `start: user={name} tg_id={id} has_role={bool} has_profile={bool}` |
| start.py | INFO | `Submitted agent_chat_task: task_id={id}` |
| tasks.py | INFO | `{task_name} completed: {details}` |
| tasks.py | EXCEPTION | `{task_name} failed` |

### LLM-метрики в логах

Каждый LLM-вызов логирует:
```
LLM response: model=openai/gpt-5.1 tokens_in=1234 tokens_out=567 len=890 key=...abcd1234
LLM tools response: model=openai/gpt-5.1 tokens_in=2345 tokens_out=123 key=...abcd1234
```

Не сохраняется в DB. Не рассчитывается стоимость. Только в text logs.

---

## Health-эндпоинты

### /health

Базовый health check. Без аутентификации.

### /monitoring/llm/health

Проверка здоровья всех API-ключей. Требует аутентификацию.

Для каждого ключа выполняет минимальный запрос к OpenRouter (model=gpt-4o-mini, max_tokens=1):

```json
{
    "keys": [
        {"key_suffix": "abcd1234", "status": "ok", "available": true},
        {"key_suffix": "efgh5678", "status": "error", "error": "HTTP 429", "available": false}
    ],
    "total": 2,
    "healthy": 1
}
```

### /monitoring/llm/stats

Статистика использования ключей из памяти. Требует аутентификацию.

```json
{
    "total_keys": 3,
    "available_keys": 2,
    "keys": [
        {
            "suffix": "abcd1234",
            "available": true,
            "fail_count": 0,
            "cooldown_remaining": 0
        },
        {
            "suffix": "efgh5678",
            "available": false,
            "fail_count": 3,
            "cooldown_remaining": 42.5
        }
    ]
}
```

### /monitoring/services

Ссылки на инфраструктурные сервисы. Без аутентификации.

```json
{
    "services": {
        "rabbitmq": {"management_ui": "https://evt-ai.ru/rabbitmq/"},
        "flower": {"ui": "https://evt-ai.ru/flower/"},
        "redis": {"url": "redis://localhost:6379/0"},
        "database": {"url": "postgresql+asyncpg://***@host:5432/db"},
        "celery": {"broker": "RabbitMQ", "backend": "Redis"}
    },
    "links": {
        "rabbitmq": "https://evt-ai.ru/rabbitmq/",
        "flower": "https://evt-ai.ru/flower/",
        "api_docs": "https://evt-ai.ru/docs",
        "admin": "https://evt-ai.ru/"
    }
}
```

### /monitoring/celery/stats

Статистика Celery workers. Требует аутентификацию.

```json
{
    "workers": ["celery@worker1"],
    "active_tasks": {"celery@worker1": 2},
    "stats": { ... }
}
```

---

## Audit trail

Таблица `AdminAuditLog` в PostgreSQL:

| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| user_id | UUID | Кто выполнил действие |
| action | String | Тип действия |
| entity_type | String | Тип сущности (project, event, ...) |
| entity_id | UUID | ID сущности |
| details | JSONB | Подробности действия |
| created_at | DateTime | Время действия |

Логирует действия организаторов в админке.

---

## Celery monitoring

- Flower UI: `https://evt-ai.ru/flower/`
- `task_track_started=True` - отслеживание начала выполнения задач
- Credentials: задаются через env vars (FLOWER_BASIC_AUTH)

---

## Offline evals

### Метрики рекомендаций

| Метрика | Значение | Описание |
|---------|---------|----------|
| NDCG@15 | 0.82 | Normalized Discounted Cumulative Gain |
| Precision@15 | 0.71 | Доля релевантных в top-15 |
| Recall@15 | 0.78 | Покрытие релевантных проектов |

### Условия эксперимента

- 10 синтетических профилей (разные роли и интересы)
- 330 проектов (реальные данные Demo Day)
- Ручная разметка релевантности: 0 (не релевантен), 1 (слабо), 2 (средне), 3 (высоко)
- 1 аннотатор

### Ограничения

- Нет бейзлайна для сравнения (random, popularity-based)
- Нет inter-annotator agreement (1 аннотатор)
- Проверочный замер, не научный результат
- Offline-оценка, без реальных пользователей

---

## PII handling

### Что не отправляется в LLM

| Данные | Обработка |
|--------|----------|
| ФИО пользователя | Не включается в промпт |
| Telegram username | Не включается в промпт |
| Telegram ID | Не включается в промпт |
| Контакты авторов проектов | Не включаются |
| Имена экспертов | Не включаются |
| Оценки экспертов | Не включаются |

### Что отправляется в LLM

| Данные | Контекст |
|--------|---------|
| Интересы, цели, роль | Профилирование, agent mode |
| Компания, должность (бизнес) | Профилирование, agent mode |
| Название, теги, описание проектов | Рекомендации, agent mode, Q&A |
| Автор проекта (только имя, не контакт) | В payload Qdrant |
| История диалога (до 20 сообщений) | Agent mode |

### Автоматическая PII-фильтрация

**Не реализована.** Фильтрация ручная (by design): промпты не содержат PII-полей.

Если пользователь сам напишет ФИО/контакты в чате -> попадет в LLM-контекст через chat history. Автоматического детектора нет.

---

## Что не логируется

| Данные | Причина |
|--------|--------|
| Prompt content | Не сохраняется ни в logs, ни в DB |
| Полные LLM-ответы | Только длина (len) |
| Пользовательские сообщения | Только в session state (PicklePersistence), не в persistent logs |
| PII | Не попадает в logs by design |
| Стоимость LLM-вызовов | Не рассчитывается |

---

## Планируемые улучшения

| Улучшение | Описание | Статус |
|-----------|---------|--------|
| Structured logging | python-json-logger, JSON-формат для парсинга | Планируется |
| Cost tracking | Таблица LlmTokenUsage: model, tokens_in, tokens_out, cost | Планируется |
| Error tracking | Sentry интеграция для exceptions | Планируется |
| Request tracing | Correlation IDs для сквозного трейсинга | Планируется |
| Metrics collection | Prometheus + Grafana для latency, throughput | Планируется |
| Online evals | User feedback signals (thumbs up/down на рекомендации) | Планируется |
| PII-фильтрация | Автоматический детектор перед отправкой в LLM | Планируется |
| Rate limiting | Ограничение запросов на пользователя | Планируется |
