#!/usr/bin/env bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE USER sql_user WITH PASSWORD 'ZBFqjaPzVCsDplKEZDzr_hnFXwyfp4Y-WR7os4hvMew';
	GRANT USAGE, CREATE ON SCHEMA public TO sql_user;



    CREATE TABLE users (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

        oauth_provider  TEXT NOT NULL,          -- google / github / etc
        oauth_user_id   TEXT NOT NULL,          -- provider 内的 user id
        email           TEXT,
        display_name    TEXT,
        avatar_url      TEXT,

        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_login_at   TIMESTAMPTZ
    );

    CREATE UNIQUE INDEX uniq_oauth_user
    ON users (oauth_provider, oauth_user_id);



    CREATE TABLE token_usage (
        id              BIGSERIAL PRIMARY KEY,
        user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        conversation_id UUID,

        tokens_in       INTEGER NOT NULL,
        tokens_out      INTEGER NOT NULL,
        model           TEXT,

        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_token_usage_user_time ON token_usage (user_id, created_at);
    CREATE INDEX idx_token_usage_conversation ON token_usage (conversation_id);



    CREATE TABLE chat_messages (
        id          BIGSERIAL PRIMARY KEY,
        user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

        role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
        content     TEXT NOT NULL,

        conversation_id UUID,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_chat_user_time
    ON chat_messages (user_id, created_at);



    CREATE TABLE conversations (
        id              BIGSERIAL PRIMARY KEY,
        user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        conversation_id UUID UNIQUE NOT NULL,
        title           TEXT,
        messages        JSONB NOT NULL DEFAULT '[]',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_conversations_user_id ON conversations(user_id);
    CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);


    GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public
    TO sql_user;

    GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public
    TO sql_user;

    ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLES TO sql_user;

    ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT
    ON SEQUENCES TO sql_user;

EOSQL




