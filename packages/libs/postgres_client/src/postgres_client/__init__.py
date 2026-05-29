import os
from contextlib import contextmanager

import boto3
import psycopg
from psycopg.rows import dict_row


class PostgresConfigurationError(RuntimeError):
    """Raised when required Postgres runtime configuration is missing."""


_connection_string_cache: str | None = None
_reusable_connection = None


def get_connection_string() -> str:
    global _connection_string_cache

    if _connection_string_cache is not None:
        return _connection_string_cache

    try:
        name = os.environ["POSTGRES_URL_PARAMETER_NAME"]
    except KeyError as exc:
        raise PostgresConfigurationError(
            "POSTGRES_URL_PARAMETER_NAME environment variable is required"
        ) from exc

    _connection_string_cache = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)[
        "Parameter"
    ]["Value"]
    return _connection_string_cache


def _new_connection():
    return psycopg.connect(
        get_connection_string(),
        row_factory=dict_row,
        prepare_threshold=None,
    )


def _connection_is_healthy(conn) -> bool:
    if conn is None or getattr(conn, "closed", False):
        return False
    try:
        conn.execute("select 1")
        conn.rollback()
        return True
    except Exception:
        return False


def get_reusable_connection():
    """Return a warm-container Postgres connection, reconnecting if it is stale or broken."""
    global _reusable_connection

    if _connection_is_healthy(_reusable_connection):
        return _reusable_connection

    if _reusable_connection is not None:
        try:
            _reusable_connection.close()
        except Exception:
            pass

    _reusable_connection = _new_connection()
    return _reusable_connection


@contextmanager
def connect():
    conn = _new_connection()
    try:
        yield conn
    finally:
        conn.close()
