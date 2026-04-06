# Memory & Context - Спецификация

Управление состоянием, историей диалога и контекстным бюджетом LLM.

Код: `backend/app/bot/app.py`, `backend/app/bot/handlers/start.py`, `backend/app/bot/handlers/shared.py`.

---

## Session state: PicklePersistence

### Хранилище

```python
persistence_path = "/app/data/bot_persistence.pickle"
persistence = PicklePersistence(filepath=persistence_path)
```

- Формат: Python pickle (бинарный)
- Расположение: Docker volume `/app/data/`
- Переживает перезапуск бота (файл на диске)
- Fallback: если persistence не создается -> in-memory state (теряется при рестарте)
- Библиотека: python-telegram-bot 21.x PicklePersistence

### Когда записывается

PicklePersistence автоматически сериализует `context.user_data` после каждого обработчика. Запись асинхронная, управляется PTB.

---

## user_data keys

| Ключ | Тип | Когда устанавливается | Описание |
|------|-----|----------------------|----------|
| `profile_id` | str (UUID) | После создания/загрузки профиля | ID записи GuestProfile |
| `profile_user_id` | str (UUID) | После создания/загрузки профиля | ID пользователя в системе |
| `profile_event_id` | str (UUID) | После создания/загрузки профиля | ID текущего мероприятия |
| `pending_role_code` | str | При выборе роли | "guest" или "business" |
| `guest_subtype` | str | При выборе подтипа гостя | "student", "applicant", "other" |
| `custom_subtype` | str | При вводе кастомного подтипа | Свободный текст |
| `nl_conversation` | list[dict] | При начале профилирования | История диалога профилирования |
| `extracted_profile` | dict | При извлечении профиля LLM | {action, interests, goals, summary, company, ...} |
| `recommendations` | dict | После генерации рекомендаций | {total, must_visit, if_time} |
| `program_chat` | list[dict] | При входе в agent mode | История чата с агентом |
| `pending_task_id` | str | При долгой генерации | ID Celery-задачи для polling |
| `support_chat_history` | str | При возврате из support chat | Текст переписки с организатором |
| `support_thread_id` | str (UUID) | При входе в support chat | ID thread в support system |
| `event_id` | str (UUID) | При /start | ID мероприятия (дублирует profile_event_id для совместимости) |
| `current_project_id` | str (UUID) | При просмотре проекта | ID проекта в VIEW_DETAIL |
| `current_project_title` | str | При просмотре проекта | Название проекта |
| `current_project_rank` | int | При просмотре проекта | Ранг проекта в рекомендациях |

---

## Chat history (agent mode)

### Формат

```python
program_chat = [
    {"role": "user", "content": "Расскажи про проект 3"},
    {"role": "assistant", "content": "Проект #3 - ..."},
    ...
]
```

### Ограничения

- Максимум 20 сообщений
- При превышении - обрезка с начала: `chat_history = chat_history[-20:]`
- Если tool уже отправил ответ (compare_projects, get_followup) -> записывается `"(результат отправлен)"`
- Каждое сообщение пользователя и ответ агента записываются в `program_chat`

### Profiling conversation (nl_conversation)

Отдельная история для диалога профилирования:
- Формат: `[{"role": "user"|"assistant", "content": "..."}]`
- Очищается при начале нового профилирования
- Не пересекается с `program_chat`
- Максимум 2 LLM-ответа (ограничение промпта), 2-3 пользовательских сообщения

---

## Context budget (LLM)

Оценка входного контекста для одного вызова agent mode:

| Компонент | Оценка (токены) | Источник |
|-----------|----------------|----------|
| System prompt | ~400 | `build_agent_system_prompt()` - роль, правила, инструкции |
| Tool definitions | ~1500 | `AGENT_TOOLS` - 7 функций с описаниями и параметрами |
| Profile info | ~200 | Теги, ключевые слова, NL-summary, компания |
| Recommendations summary | ~2000 | До 15 проектов: rank, title, score, tags[:3], room, summary[:150] |
| Support chat history | ~500 | Опционально, при возврате из support chat |
| Chat history (20 msg) | ~4000 | До 20 сообщений user+assistant |
| **Итого** | **~8600** | Без ответа модели |

При использовании GPT-5.1 (128K context) бюджет составляет ~7% от доступного окна. Запас достаточный.

### Recommendations summary format

```
#1 LLM-чат-бот - 87.5% | tags: NLP, Agents, LLM | Зал 1 | Проект реализует чат-бота для...
#2 AI-скоринг - 82.3% | tags: ML, Finance | Зал 3 | Система автоматической оценки...
...
```

Каждая строка: `~150 символов` -> ~40 токенов. 15 проектов -> ~600 токенов чистого текста, с форматированием ~2000.

---

## DB persistence (долгосрочное)

### GuestProfile

| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| user_id | UUID | FK -> users |
| event_id | UUID | FK -> events |
| selected_tags | ARRAY[String] | Теги из профилирования |
| extracted_tags | ARRAY[String] | Не используется (legacy) |
| keywords | ARRAY[String] | Цели/ключевые слова |
| raw_text | Text | Сырой текст диалога профилирования |
| extra_data | JSONB | {nl_summary, company, position, partner_status, business_objectives} |

### BusinessProfile

Аналогичная структура для бизнес-партнеров. Поля extra_data включают:
- company, position, partner_status, business_objectives

### Recommendation

| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| guest_profile_id | UUID | FK -> guest_profiles |
| project_id | UUID | FK -> projects |
| rank | Integer | Позиция в списке (1-15) |
| relevance_score | Float | 0-100 |
| category | String | "must_visit" или "if_time" |
| llm_summary | Text | LLM-резюме или первые 2 предложения |

---

## Recovery

### При /start (returning user)

```python
# Проверка: есть роль + есть профиль с тегами?
role = get_user_role_with_info(session, user.id, event.id)
profile = get_or_create_profile(session, user.id, event.id)
has_profile = bool(profile.selected_tags)
```

Варианты:
1. `role + profile` -> прямой вход в VIEW_PROGRAM, загрузка рекомендаций
2. `role + no profile` -> продолжение профилирования (ONBOARD_NL_PROFILE)
3. `no role` -> стандартный онбординг (CHOOSE_ROLE)

### Orphan messages (после рестарта контейнера)

Если пользователь пишет текст вне ConversationHandler (state потерян):
1. Проверка наличия профиля в DB
2. Если есть -> "Сессия была перезапущена. Отправьте /start - я восстановлю вашу программу."
3. Если нет -> "Отправьте /start для начала работы с ботом."

Обработчик: `orphan_text_handler()` - catch-all для текстовых сообщений вне ConversationHandler.

---

## Memory policy

| Аспект | Политика |
|--------|---------|
| Cross-session memory | Нет. Только профиль (DB) и PicklePersistence |
| Долгосрочное хранение диалогов | Нет. program_chat живет в session state |
| Логирование диалогов | В support_messages (DB) для видимости организатора. Не для LLM-контекста |
| Забывание | program_chat обрезается до 20 сообщений. При rebuild_profile - полный сброс |
| Персистентность | PicklePersistence -> file на диске. DB -> PostgreSQL. Qdrant -> vector storage |
| PII в памяти | ФИО, username хранятся в DB (users table). Не попадают в LLM-контекст |
