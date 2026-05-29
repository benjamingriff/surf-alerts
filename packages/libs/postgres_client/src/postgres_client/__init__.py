import os
from contextlib import contextmanager

import boto3
import psycopg
from psycopg.rows import dict_row


class PostgresConfigurationError(RuntimeError):
    """Raised when required Postgres runtime configuration is missing."""


def get_connection_string() -> str:
    try:
        name = os.environ["POSTGRES_URL_PARAMETER_NAME"]
    except KeyError as exc:
        raise PostgresConfigurationError(
            "POSTGRES_URL_PARAMETER_NAME environment variable is required"
        ) from exc

    return boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


@contextmanager
def connect():
    conn = psycopg.connect(
        get_connection_string(),
        row_factory=dict_row,
        prepare_threshold=None,
    )
    try:
        yield conn
    finally:
        conn.close()
