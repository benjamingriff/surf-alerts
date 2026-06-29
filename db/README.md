# Database migrations

Base Postgres tables are managed with plain SQL in `db/migrations/`.

For this learning phase, migrations are applied manually by the project owner, not by CI/CD. See [Manual RDS Setup](../docs/operations/rds-setup.md) for the full runbook.

## Fresh RDS deployments

Apply these migrations, in order:

1. `0001_create_discovery_spot_versions.sql` — processed spot discovery state.
2. `0003_create_partitioned_forecast_tables.sql` — partitioned forecast hot store schema with default and initial daily UTC partitions.

Do **not** apply `0002_create_forecast_tables.sql` to fresh RDS deployments. It is the historical non-partitioned forecast migration and is retained only as schema history.
