import os
from contextlib import contextmanager

import boto3
import psycopg
from psycopg.rows import dict_row


def get_connection_string(parameter_name: str | None = None) -> str:
    name = parameter_name or os.environ["SUPABASE_POSTGRES_URL_PARAMETER_NAME"]
    return boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


@contextmanager
def connect(parameter_name: str | None = None):
    conn = psycopg.connect(get_connection_string(parameter_name), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
