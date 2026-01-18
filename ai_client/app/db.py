"""
Database utilities for user management and chat history
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager


def get_db_config():
    """Get database configuration from environment variables"""
    return {
        "host": os.getenv("POSTGRES_HOST"),
        "port": int(os.getenv("POSTGRES_PORT")),
        "database": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }


@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        conn = psycopg2.connect(**get_db_config())
        yield conn
    finally:
        if conn:
            conn.close()


def get_or_create_user(oauth_provider: str, email: str, display_name: str = None, avatar_url: str = None) -> dict:
    """
    Get existing user or create new one based on OAuth provider and email.
    Uses email as oauth_user_id since it should be unique.
    Returns user dict with id and other fields.
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Try to find existing user
            cur.execute(
                """
                SELECT id, oauth_provider, oauth_user_id, email, display_name, avatar_url, created_at, last_login_at
                FROM users
                WHERE oauth_provider = %s AND oauth_user_id = %s
                """,
                (oauth_provider, email)
            )
            user = cur.fetchone()

            if user:
                # Update last login time
                cur.execute(
                    "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                    (user["id"],)
                )
                conn.commit()
                return dict(user)

            # Create new user
            cur.execute(
                """
                INSERT INTO users (oauth_provider, oauth_user_id, email, display_name, avatar_url, last_login_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                RETURNING id, oauth_provider, oauth_user_id, email, display_name, avatar_url, created_at, last_login_at
                """,
                (oauth_provider, email, email, display_name, avatar_url)
            )
            new_user = cur.fetchone()
            conn.commit()
            return dict(new_user)


def save_chat_message(user_id: str, role: str, content: str, conversation_id: str) -> int:
    """Save a chat message to the database"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (user_id, role, content, conversation_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, role, content, conversation_id)
            )
            message_id = cur.fetchone()[0]
            conn.commit()
            return message_id


def get_chat_history(user_id: str, conversation_id: str = None, limit: int = 50) -> list:
    """Get chat history for a user"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if conversation_id:
                cur.execute(
                    """
                    SELECT role, content, created_at
                    FROM chat_messages
                    WHERE user_id = %s AND conversation_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (user_id, conversation_id, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT role, content, created_at
                    FROM chat_messages
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, limit)
                )
            return [dict(row) for row in cur.fetchall()]


def record_token_usage(user_id: str, tokens_in: int, tokens_out: int, model: str = None):
    """Record token usage for a user"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO token_usage (user_id, tokens_in, tokens_out, model)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, tokens_in, tokens_out, model)
            )
            conn.commit()


def get_user_token_stats(user_id: str) -> dict:
    """Get total token usage stats for a user"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(tokens_in), 0) as total_tokens_in,
                    COALESCE(SUM(tokens_out), 0) as total_tokens_out,
                    COUNT(*) as total_requests
                FROM token_usage
                WHERE user_id = %s
                """,
                (user_id,)
            )
            return dict(cur.fetchone())
