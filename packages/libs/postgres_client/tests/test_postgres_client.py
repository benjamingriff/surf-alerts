import pytest

import postgres_client
from postgres_client import PostgresConfigurationError, get_connection_string


class FakeSsmClient:
    def __init__(self):
        self.calls = []

    def get_parameter(self, **kwargs):
        self.calls.append(kwargs)
        return {"Parameter": {"Value": "postgres://user:pass@host:5432/db"}}


def test_get_connection_string_requires_postgres_url_parameter_name(monkeypatch):
    monkeypatch.delenv("POSTGRES_URL_PARAMETER_NAME", raising=False)

    with pytest.raises(PostgresConfigurationError, match="POSTGRES_URL_PARAMETER_NAME"):
        get_connection_string()


def test_get_connection_string_reads_new_postgres_parameter(monkeypatch):
    client = FakeSsmClient()
    monkeypatch.setenv("POSTGRES_URL_PARAMETER_NAME", "/surf-alerts/rds/postgres-url")
    monkeypatch.setattr(postgres_client.boto3, "client", lambda service: client)

    assert get_connection_string() == "postgres://user:pass@host:5432/db"
    assert client.calls == [
        {"Name": "/surf-alerts/rds/postgres-url", "WithDecryption": True}
    ]
