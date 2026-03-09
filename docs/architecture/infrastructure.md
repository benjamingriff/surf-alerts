# Infrastructure

> **Status: IMPLEMENTED** | Last verified: 2026-03-08

AWS CDK (TypeScript) infrastructure in `infrastructure/`.

## Stack: SufAlertsStack

### S3 Data Bucket

- Name: `{stack-name}-data` (lowercase)
- Encryption: S3-managed
- Removal policy: RETAIN (data preserved on stack deletion)

### ScraperWorker Construct

Creates a Docker Lambda with SQS trigger for on-demand scraping.

```typescript
interface ScraperWorkerProps {
  projectName: string;
  scraperName: string;
  codePath: string;
  timeout: number;         // seconds
  memorySize: number;      // MB
  maxConcurrency?: number; // default: 2
}
```

**Active workers:**

| Worker | Timeout | Memory | Max Concurrency |
|--------|---------|--------|-----------------|
| Spot Scraper | 60s | 1024 MB | 5 |
| Forecast Scraper | 60s | 1024 MB | 2 |

**Components per worker:**
- Docker Lambda (Python 3.12, built from package Dockerfile)
- SQS queue with DLQ (via SqsQueue construct)
- Event source mapping (batch size: 1, reports batch item failures)
- S3 read/write permissions on data bucket
- Environment: `POWERTOOLS_LOG_LEVEL=INFO`

### SqsQueue Construct

```typescript
interface SqsQueueProps {
  queueName: string;
  visibilityTimeout: cdk.Duration;
}
```

| Setting | Main Queue | Dead-Letter Queue |
|---------|-----------|-------------------|
| Retention | 1 day | 7 days |
| Visibility timeout | 3x function timeout | Default |
| Max receive count | 3 | — |
| Name | `{project}-{scraper}-queue` | `{queue-name}-dlq` |

### ScheduledScraper Construct

Creates a Docker Lambda triggered by EventBridge cron. Currently **disabled** for all scheduled scrapers.

| Scraper | Schedule | Timeout | Notes |
|---------|----------|---------|-------|
| Sitemap Scraper | 06:00 UTC | 60s | Disabled |
| Taxonomy Scraper | 06:00 UTC | 600s (10min) | Disabled, legacy recursive API calls |
| Spot Reconciler | 06:15 UTC | 60s | Disabled, legacy discovery job |

**Components per scheduled scraper:**
- Docker Lambda
- EventBridge rule with cron schedule
- S3 read/write permissions
- Environment: `BUCKET_NAME` injected

## Planned Discovery Processors

The target discovery design adds Lambda-style processors downstream of raw S3 writes:

| Processor | Trigger | Role |
|-----------|---------|------|
| Discovery Diff | S3 object created on `raw/sitemap/...` | Emits `added` / `removed` events and queues new spot IDs |
| Spot Report Processor | S3 object created on `raw/spot_report/...` | Computes checksums and appends discovery version rows |
| Catalog Builder | Processing manifest or S3 event | Rebuilds `processed/discovery/catalog_latest/` |

These processors are planned only. They are not currently defined in the CDK stack.

### CI/CD IAM (GitHubActionsCdkDeployRole)

OIDC-based GitHub Actions authentication (no static AWS keys).

- OIDC Provider: `https://token.actions.githubusercontent.com`
- Role: `GitHubActionsCdkDeployRole`
- Trust: GitHub actions from `benjamingriff/surf-alerts` on `main`
- Permissions: Assume CDK qualification roles (`cdk-hnb659fds-*`)

## CDK Commands

```bash
cd infrastructure
npm ci              # Install dependencies
npm run build       # Compile TypeScript
npm test            # Run CDK tests
npx cdk synth       # Synthesize CloudFormation
npx cdk deploy SufAlertsStack --require-approval never
```
