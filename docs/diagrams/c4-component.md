# C4 Component - Telegram Bot (Agent Core)

Внутренняя структура Telegram-бота - ядро агентской системы.

```mermaid
flowchart TB
    telegram["Telegram API<br/><i>updates, сообщения</i>"]

    subgraph bot["Telegram Bot (PTB 21.x)"]
        direction TB

        subgraph fsm["State Machine"]
            conv["ConversationHandler<br/><i>7 состояний,<br/>переходы между фазами</i>"]
        end

        subgraph handlers["Обработчики состояний"]
            profiler["Profiler<br/><i>NL-профилирование,<br/>макс. 2 уточнения,<br/>JSON-профиль</i>"]
            agent_mode["AgentMode<br/><i>tool calling, диалог с LLM,<br/>chat_history до 20 msg</i>"]
            support["SupportChat<br/><i>вопрос -> админка -> ответ</i>"]
        end

        subgraph tools["Инструменты"]
            tool_dispatch["ToolDispatcher<br/><i>whitelist, валидация, роль-доступ</i>"]
            tool_list["show_project | show_profile<br/>compare_projects | generate_questions<br/>get_followup | get_pipeline<br/>rebuild_profile"]
        end

        subgraph services["Сервисы"]
            llm_client["LLM Client<br/><i>key rotation, fallback GPT-4o-Mini,<br/>retry 3x, exp backoff</i>"]
            embedding["Embedding Service<br/><i>Gemini 768d, Qdrant client</i>"]
            retriever["Retriever<br/><i>embed -> Qdrant top-30 -><br/>rerank -> LLM-резюме -> top-15</i>"]
        end
    end

    subgraph external["Внешние зависимости"]
        openrouter["OpenRouter<br/><i>Chat Completions</i>"]
        qdrant["Qdrant<br/><i>vector search</i>"]
        pg[("PostgreSQL<br/><i>профили, проекты</i>")]
        celery["Celery Worker<br/><i>async tasks</i>"]
    end

    telegram -->|"messages, callbacks"| conv
    conv -->|"ONBOARD_NL_PROFILE"| profiler
    conv -->|"VIEW_PROGRAM"| agent_mode
    conv -->|"SUPPORT_CHAT"| support

    profiler -->|"profile prompt"| llm_client
    agent_mode -->|"system prompt + tools"| llm_client
    agent_mode -->|"tool_call"| tool_dispatch
    tool_dispatch --- tool_list
    tool_dispatch -->|"данные"| pg

    retriever -->|"embed text"| embedding
    retriever -->|"LLM summaries"| llm_client

    llm_client -->|"HTTP"| openrouter
    llm_client -->|"async tasks"| celery
    embedding -->|"HTTP embeddings"| openrouter
    embedding -->|"search/upsert"| qdrant
    support -->|"threads"| pg
```
