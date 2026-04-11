-- EventAI Agent - Database Schema (13 tables)
-- Idempotent: all statements use IF NOT EXISTS / DO NOTHING

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Enum for user roles
DO $$ BEGIN
    CREATE TYPE role_enum AS ENUM ('guest', 'business', 'expert');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- Core tables (5, read-only at runtime)
-- ============================================================

CREATE TABLE IF NOT EXISTS events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    description TEXT,
    evaluation_criteria JSONB,
    timezone    TEXT NOT NULL DEFAULT 'Europe/Moscow',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS projects (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id          UUID NOT NULL REFERENCES events(id),
    title             TEXT NOT NULL,
    description       TEXT NOT NULL,
    author            TEXT,
    telegram_contact  TEXT,
    track             TEXT,
    tags              JSONB,
    tech_stack        JSONB,
    github_url        TEXT,
    presentation_url  TEXT,
    parsed_content    JSONB,
    embedding         vector(3072)
);

CREATE INDEX IF NOT EXISTS idx_projects_event_id ON projects(event_id);

CREATE TABLE IF NOT EXISTS rooms (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id      UUID NOT NULL REFERENCES events(id),
    name          TEXT NOT NULL,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS schedule_slots (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id    UUID NOT NULL REFERENCES events(id),
    room_id     UUID NOT NULL REFERENCES rooms(id),
    project_id  UUID NOT NULL REFERENCES projects(id),
    start_time  TIMESTAMP NOT NULL,
    end_time    TIMESTAMP NOT NULL,
    day_number  INTEGER NOT NULL,
    UNIQUE (room_id, start_time)
);

CREATE INDEX IF NOT EXISTS idx_schedule_slots_event_id ON schedule_slots(event_id);
CREATE INDEX IF NOT EXISTS idx_schedule_slots_start_time ON schedule_slots(start_time);

CREATE TABLE IF NOT EXISTS roles (
    id   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

-- ============================================================
-- User + Profile tables (4)
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_user_id TEXT NOT NULL UNIQUE,
    full_name        TEXT NOT NULL,
    username         TEXT,
    role_code        role_enum,
    subrole          TEXT,
    created_at       TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_user_id ON users(telegram_user_id);

CREATE TABLE IF NOT EXISTS guest_profiles (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id),
    event_id            UUID NOT NULL REFERENCES events(id),
    selected_tags       JSONB,
    keywords            JSONB,
    raw_text            TEXT,
    nl_summary          TEXT,
    company             TEXT,
    position            TEXT,
    objective           TEXT,
    business_objectives JSONB,
    created_at          TIMESTAMP NOT NULL DEFAULT now(),
    updated_at          TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_guest_profiles_event_id ON guest_profiles(event_id);

CREATE TABLE IF NOT EXISTS recommendations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id      UUID NOT NULL REFERENCES guest_profiles(id),
    project_id      UUID NOT NULL REFERENCES projects(id),
    relevance_score DOUBLE PRECISION NOT NULL,
    category        TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    slot_id         UUID REFERENCES schedule_slots(id),
    visit_order     INTEGER,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (profile_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_profile_id ON recommendations(profile_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id),
    event_id   UUID NOT NULL REFERENCES events(id),
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);

-- ============================================================
-- Expert tables (2)
-- ============================================================

CREATE TABLE IF NOT EXISTS experts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) UNIQUE,
    event_id    UUID NOT NULL REFERENCES events(id),
    invite_code TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    room_id     UUID REFERENCES rooms(id),
    tags        JSONB,
    bot_started BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_experts_invite_code ON experts(invite_code);

CREATE TABLE IF NOT EXISTS expert_scores (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    expert_id       UUID NOT NULL REFERENCES experts(id),
    project_id      UUID NOT NULL REFERENCES projects(id),
    criteria_scores JSONB NOT NULL,
    comment         TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP,
    UNIQUE (expert_id, project_id)
);

-- ============================================================
-- Support + Business tables (2)
-- ============================================================

CREATE TABLE IF NOT EXISTS support_log (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id        UUID NOT NULL REFERENCES users(id),
    event_id       UUID NOT NULL REFERENCES events(id),
    correlation_id TEXT NOT NULL UNIQUE,
    question       TEXT NOT NULL,
    answer         TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT now(),
    answered_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_support_log_user_id ON support_log(user_id);
CREATE INDEX IF NOT EXISTS idx_support_log_correlation_id ON support_log(correlation_id);

CREATE TABLE IF NOT EXISTS business_followups (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id),
    event_id   UUID NOT NULL REFERENCES events(id),
    project_id UUID NOT NULL REFERENCES projects(id),
    status     TEXT NOT NULL DEFAULT 'interested',
    notes      TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP
);
