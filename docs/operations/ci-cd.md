# CI/CD

> **Status: IMPLEMENTED** | Last verified: 2026-03-08

GitHub Actions deploys the CDK stack on push to `main` using OIDC authentication (no static AWS keys).

## Workflow

**File:** `.github/workflows/deploy.yaml`

**Trigger:** Push to `main` branch

### Pipeline Steps

1. **Checkout** — `actions/checkout@v4`
2. **Setup Node** — Node.js 20 via `actions/setup-node@v4`
3. **OIDC Authentication** — `aws-actions/configure-aws-credentials@v4`
   - Role: `arn:aws:iam::{AWS_ACCOUNT_ID}:role/GitHubActionsCdkDeployRole`
   - Region: from `vars.AWS_REGION`
4. **Verify Credentials** — `aws sts get-caller-identity`
5. **Install Dependencies** — `npm ci` in `infrastructure/`
6. **CDK Synth** — `npx cdk synth` in `infrastructure/`
7. **CDK Deploy** — `npx cdk deploy SufAlertsStack --require-approval never`

## Required GitHub Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AWS_ACCOUNT_ID` | AWS account number | `123456789012` |
| `AWS_REGION` | AWS region | `eu-west-2` |

## OIDC Authentication

No static AWS keys are stored. Authentication uses GitHub's OIDC provider:

- **OIDC Provider:** `https://token.actions.githubusercontent.com`
- **IAM Role:** `GitHubActionsCdkDeployRole`
- **Trust policy:** Only allows GitHub Actions from `benjamingriff/surf-alerts` on `main`
- **Permissions:** Assume CDK qualification roles (`cdk-hnb659fds-*`)

The IAM role and OIDC provider are defined in the CDK stack (`lib/ci-iam-stack.ts`).

## Permissions

```yaml
permissions:
  id-token: write   # Required for OIDC
  contents: read     # Required for checkout
```
