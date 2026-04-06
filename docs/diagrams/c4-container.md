# C4 Container - EventAI Agent

Контейнеры системы EventAI с фокусом на агентскую часть. Web Admin - внешняя система.

```mermaid
C4Container
    title EventAI Agent - Container Diagram

    Person(user, "Пользователь", "Гость / Эксперт / Бизнес-партнер")

    System_Boundary(eventai, "EventAI System") {

        Container(bot, "Telegram Bot", "python-telegram-bot 21.x", "ConversationHandler, agent mode, 7 состояний")
        Container(api, "FastAPI Backend", "Python, FastAPI", "REST API, 87 эндпоинтов, бизнес-логика")
        Container(celery, "Celery Worker", "Python, Celery", "Async LLM tasks, reranking, рекомендации")

        ContainerDb(pg, "PostgreSQL", "SQL", "Профили, рекомендации, эксперты, аудит")
        ContainerDb(qdrant, "Qdrant", "Vector DB", "Эмбеддинги проектов, cosine similarity")
        ContainerDb(redis, "Redis", "In-memory", "Celery result backend, кэш")
        Container(rabbitmq, "RabbitMQ", "AMQP", "Message broker для Celery")

    }

    System_Boundary(observability, "Observability") {
        Container(flower, "Flower", "Python", "Celery monitoring UI, task history, worker stats")
        Container(health, "Health/Monitoring", "FastAPI endpoints", "/health, /monitoring/llm/*, /monitoring/celery/*")
        Container(logging, "Logging", "Python logging", "model, tokens, latency, key_id (stdout -> Docker logs)")
    }

    System_Ext(telegram, "Telegram API", "Доставка сообщений")
    System_Ext(openrouter, "OpenRouter", "LLM API: GPT-5.1, GPT-4o-Mini, Gemini Embeddings")
    System_Ext(web_admin, "Web Admin", "React 19 - админка организатора (external)")

    Rel(user, telegram, "Сообщения, кнопки")
    Rel(telegram, bot, "Updates (polling/webhook)")
    Rel(bot, api, "HTTP: профили, проекты, рекомендации")
    Rel(bot, celery, "Tasks: agent_chat, generate_recommendations")
    Rel(celery, openrouter, "Chat Completions, Embeddings")
    Rel(celery, qdrant, "Vector search, upsert")
    Rel(celery, pg, "R/W: профили, рекомендации")
    Rel(celery, rabbitmq, "AMQP: task queue")
    Rel(celery, redis, "Result backend")
    Rel(api, pg, "SQL queries")
    Rel(api, qdrant, "Vector queries")
    Rel(web_admin, api, "REST API: данные, ответы на вопросы")

    Rel(flower, celery, "Inspect: active tasks, workers")
    Rel(health, api, "Status: LLM keys, Celery, services")
    Rel(logging, bot, "stdout: handler logs")
    Rel(logging, celery, "stdout: task logs, LLM metrics")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="2")
```
