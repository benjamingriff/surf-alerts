# Manual RDS Setup

> **Status: LEARNING-PHASE MANUAL RUNBOOK**

This project does not have a migration runner yet. Fresh RDS setup is a manual workflow: deploy the CDK stack, retrieve the generated RDS credentials, create the application connection URL, store it in SSM Parameter Store, and apply the intended SQL migrations with `psql`.

## Fresh RDS migration set

Apply these migrations to a fresh RDS database, in order:

1. `db/migrations/0001_create_discovery_spot_versions.sql`
   - Creates durable processed spot discovery state.
2. `db/migrations/0003_create_partitioned_forecast_tables.sql`
   - Creates the partitioned forecast hot store tables.
   - Creates default partitions as a safety net.
   - Creates initial UTC daily partitions from the current UTC date through four days ahead.

Do **not** apply `db/migrations/0002_create_forecast_tables.sql` to fresh RDS deployments. It is the historical non-partitioned forecast schema and is retained only to preserve schema history.

Example:

```bash
psql "$POSTGRES_URL" -f db/migrations/0001_create_discovery_spot_versions.sql
psql "$POSTGRES_URL" -f db/migrations/0003_create_partitioned_forecast_tables.sql
```

## Retrieve generated RDS connection details

The CDK stack provisions the database as `surf-alerts-processed-state` with database name `surf_alerts` and generated credentials in Secrets Manager under `surf-alerts/postgres/app-credentials`.

Retrieve the endpoint and secret:

```bash
aws rds describe-db-instances \
  --db-instance-identifier surf-alerts-processed-state \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text

aws secretsmanager get-secret-value \
  --secret-id surf-alerts/postgres/app-credentials \
  --query SecretString \
  --output text
```

Build an application URL in this shape:

```text
postgresql://<username>:<url-encoded-password>@<rds-endpoint>:5432/surf_alerts?sslmode=require
```

URL-encode the password before placing it in the URL, especially if it contains characters such as `@`, `/`, `:`, `#`, `%`, or `?`.

## Store the application URL in SSM

Lambdas read the database URL from the SSM SecureString parameter `/surf-alerts/rds/postgres-url`, exposed to runtime code via `POSTGRES_URL_PARAMETER_NAME`.

Create or update the parameter:

```bash
aws ssm put-parameter \
  --name /surf-alerts/rds/postgres-url \
  --type SecureString \
  --value "$POSTGRES_URL" \
  --overwrite
```

After storing it, redeploy or invoke the Postgres-using Lambdas only after the parameter exists. The CDK grants those Lambdas read access to this exact parameter.

## Temporary security posture

The current RDS instance is publicly accessible and its security group allows public TCP/5432 ingress. This is an intentional learning-phase compromise so SQL can be applied manually and the workload can be validated directly.

Security hardening is a fast follow and should include:

- moving RDS to private subnets;
- restricting database ingress to known admin and Lambda paths;
- deciding on VPC Lambda networking, VPC endpoints, NAT, or bastion/SSM admin access;
- evaluating RDS Proxy for connection management;
- adding alarms and operational dashboards.
