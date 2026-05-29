import pytest

import postgres_client
from postgres_client import PostgresConfigurationError, connect, get_connection_string, get_reusable_connection


class FakeSsmClient:
    def __init__(self):
        self.calls = []

    def get_parameter(self, **kwargs):
        self.calls.append(kwargs)
        return {"Parameter": {"Value": "postgres://user:pass@host:5432/db"}}


class FakeConnection:
    def __init__(self, *, healthy=True, closed=False):
        self.healthy = healthy
        self.closed = closed
        self.closed_by_client = False
        self.executed = []
        self.rollbacks = 0

    def execute(self, sql):
        if not self.healthy:
            raise RuntimeError("connection is stale")
        self.executed.append(sql)

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed_by_client = True
        self.closed = True


@pytest.fixture(autouse=True)
def reset_postgres_client_state(monkeypatch):
    monkeypatch.setattr(postgres_client, "_connection_string_cache", None)
    monkeypatch.setattr(postgres_client, "_reusable_connection", None)


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


def test_get_connection_string_caches_ssm_value_for_warm_container(monkeypatch):
    client = FakeSsmClient()
    monkeypatch.setenv("POSTGRES_URL_PARAMETER_NAME", "/surf-alerts/rds/postgres-url")
    monkeypatch.setattr(postgres_client.boto3, "client", lambda service: client)

    assert get_connection_string() == "postgres://user:pass@host:5432/db"
    assert get_connection_string() == "postgres://user:pass@host:5432/db"
    assert len(client.calls) == 1


def test_get_reusable_connection_reuses_existing_healthy_connection(monkeypatch):
    created = []

    def fake_connect(*args, **kwargs):
        conn = FakeConnection()
        created.append((conn, args, kwargs))
        return conn

    monkeypatch.setattr(postgres_client.psycopg, "connect", fake_connect)
    monkeypatch.setattr(postgres_client, "get_connection_string", lambda: "postgres://db")

    first = get_reusable_connection()
    second = get_reusable_connection()

    assert second is first
    assert len(created) == 1
    assert first.executed == ["select 1"]
    assert first.rollbacks == 1


def test_get_reusable_connection_reconnects_closed_connection(monkeypatch):
    stale = FakeConnection(closed=True)
    fresh = FakeConnection()
    monkeypatch.setattr(postgres_client, "_reusable_connection", stale)
    monkeypatch.setattr(postgres_client, "_new_connection", lambda: fresh)

    assert get_reusable_connection() is fresh
    assert stale.closed_by_client is True


def test_get_reusable_connection_reconnects_broken_connection(monkeypatch):
    stale = FakeConnection(healthy=False)
    fresh = FakeConnection()
    monkeypatch.setattr(postgres_client, "_reusable_connection", stale)
    monkeypatch.setattr(postgres_client, "_new_connection", lambda: fresh)

    assert get_reusable_connection() is fresh
    assert stale.closed_by_client is True


def test_connect_context_manager_still_opens_and_closes_scoped_connection(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(postgres_client, "_new_connection", lambda: conn)

    with connect() as scoped_conn:
        assert scoped_conn is conn
        assert conn.closed_by_client is False

    assert conn.closed_by_client is True
