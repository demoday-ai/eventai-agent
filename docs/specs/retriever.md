# Retriever - Спецификация

Retrieval pipeline: от профиля пользователя до персональной программы проектов.

Код: `backend/app/services/guest/profiling_service.py`, `backend/app/services/core/embedding_service.py`.

---

## Источники данных

| Источник | Что хранит | Формат |
|----------|-----------|--------|
| PostgreSQL (projects) | Название, описание, автор, теги, зал | Реляционная таблица, связь с tags и room_assignments |
| Qdrant (collection "projects") | Эмбеддинги проектов с payload | Вектор 768d + payload (event_id, project_id, title, description[:500], tags, author, room_name, room_number) |
| GuestProfile (PostgreSQL) | Профиль пользователя | selected_tags, keywords, raw_text, extra_data (nl_summary, company, business_objectives) |

---

## Индексация

Запускается при импорте/обновлении проектов через Celery-задачу `embed_projects_task`.

### Модель эмбеддинга

- Модель: `google/gemini-embedding-001`
- Размерность: 768
- API: OpenRouter Embeddings API (`{base_url}/embeddings`)
- Таймаут: 30 секунд (одиночный), 60 секунд (batch)

### Процесс

1. Загрузить все проекты мероприятия с тегами и залами из PostgreSQL
2. Построить текст для каждого проекта: `{title}. {description}. Теги: {tag1, tag2, ...}`
3. Embed пакетами по 50 (`EMBED_BATCH_SIZE = 50`) через `embed_texts_batch()`
4. Upsert в Qdrant collection "projects"

### Collection config

```
collection_name: "projects"
vector_size: 768
distance: COSINE
```

Коллекция создается автоматически при первом обращении (`_ensure_collection()`).

### Payload в Qdrant

Каждая точка хранит:
- `event_id` (string) - для фильтрации по мероприятию
- `project_id` (string)
- `title` (string)
- `description` (string, обрезано до 500 символов)
- `tags` (list[string])
- `author` (string)
- `room_name` (string | null)
- `room_number` (int | null)

---

## Retrieval pipeline

Оркестрирует `generate_recommendations()` в `profiling_service.py`.

### 1. Сборка profile text

Композиция текста из всех доступных данных профиля:

```
parts = [
    nl_summary,              # NL-описание из профилирования
    "Интересы: tag1, tag2",  # selected_tags
    "Цели: goal1, goal2",    # keywords
    "Компания: X",           # extra_data.company (бизнес)
    "Бизнес-цели: a, b",    # extra_data.business_objectives
    raw_text[:500]           # сырой текст диалога (обрезан)
]
profile_text = ". ".join(parts)
```

Fallback: если ни одного поля нет -> `"Интерес к AI проектам"`.

### 2. Эмбеддинг профиля

Один вызов `embed_text(profile_text)` -> вектор 768d.

При ошибке: `profile_embedding = None`, переход к fallback (шаг 3b).

### 3a. Qdrant similarity search

```python
find_similar(profile_embedding, event_id, limit=30)
```

- Фильтр: `event_id == текущее_мероприятие`
- Лимит: 30 результатов
- Cosine similarity, нормализация: `score * 100` -> диапазон 0-100

### 3b. Fallback (без эмбеддингов)

Если эмбеддинг не удался или Qdrant вернул пустой результат:

1. Загрузить 30 проектов напрямую из PostgreSQL (с тегами и залами)
2. Scoring: пересечение тегов проекта с тегами профиля
3. Формула: `overlap_count * 20.0`
4. Сортировка по score по убыванию

### 4. Schedule-aware reranking

Функция `schedule_rerank()`. Детерминированная, без LLM.

Для каждого кандидата (в порядке текущего ранжирования):

- **room_bonus**: если проект в зале, уже встречавшемся в рекомендациях -> `score += 3.0` (меньше перемещений)
- **conflict_penalty**: если в зале уже несколько проектов -> `score -= 2.0 * (room_count - 1)` (невозможно посетить все)

Результат сортируется по score по убыванию.

### 5. Top-15 selection

Берутся первые 15 проектов после reranking.

### 6. Padding

Если результатов < 10:
- Загрузить дополнительные проекты из PostgreSQL
- Исключить уже выбранные
- Сортировка по `created_at` (сначала новые)
- Дополнить до 10 проектов с `score = 0.0`

### 7. LLM-резюме

Batch-генерация через `generate_llm_summaries()` для top-15:

- Вход: профиль гостя (теги, keywords, company, business_objectives) + список проектов (id, title, description, tags)
- Системный промпт: `SUMMARY_SYSTEM` - "сгенерируй 2-3 предложения, адаптированные под интересы гостя"
- json_mode=True, формат: `{"summaries": [{"project_id": "...", "summary": "..."}, ...]}`
- Fallback при ошибке: `summary = None` для всех проектов

### 8. Summary fallback

Если LLM-резюме отсутствует для проекта:
- Взять первые 2 предложения description (split по ".")
- Добавить "." в конец, если отсутствует

### 9. Score normalization

```python
if max_score > 100:
    score = score / max_score * 100
else:
    score = round(score, 1)
```

Диапазон: 0-100, округление до 1 десятичного знака.

### 10. Категоризация и сохранение

- Первые 8 -> `category = "must_visit"`
- Остальные -> `category = "if_time"`
- Удаление старых рекомендаций для профиля
- Сохранение в таблицу `Recommendation` (guest_profile_id, project_id, relevance_score, category, rank, llm_summary)

---

## Выходной формат

```python
{
    "profile_id": "uuid",
    "total": 15,
    "must_visit": [
        {
            "project_id": "uuid",
            "rank": 1,
            "title": "...",
            "summary": "LLM-резюме или первые 2 предложения",
            "tags": ["NLP", "Agents"],
            "author": "...",
            "room_name": "Зал A",
            "room_number": 1,
            "relevance_score": 87.5,
            "conflict_rooms": [2, 4]
        },
        ...  # 8 проектов
    ],
    "if_time": [
        ...  # 7 проектов
    ]
}
```

---

## Ограничения

| Параметр | Значение |
|----------|---------|
| Qdrant | Single-node, без шардирования |
| Embedding API latency | ~1-2 секунды |
| Полный pipeline (embed + search + rerank + summaries) | ~5-10 секунд |
| Размер collection | До ~1000 проектов (одно мероприятие) |
| Embedding batch size | 50 проектов за запрос |
| Description в payload | Обрезано до 500 символов |
| Profile raw_text | Обрезано до 500 символов |

---

## Degradation chain

```
embed_text() OK + Qdrant OK     -> полный pipeline
embed_text() FAIL               -> tag overlap scoring (без эмбеддингов)
Qdrant пустой результат         -> tag overlap scoring (без эмбеддингов)
generate_llm_summaries() FAIL   -> первые 2 предложения description
< 10 результатов                -> padding популярными проектами
0 проектов в мероприятии        -> {"no_projects": True}
```
