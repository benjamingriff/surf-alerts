# Database migrations

Base Supabase/Postgres tables are managed with plain SQL in `db/migrations/`.

For v1 these migrations are applied manually by the project owner, not by CI/CD. Apply `0001_create_discovery_spot_versions.sql` in the Supabase SQL editor or with `psql` before deploying the discovery pipeline.
