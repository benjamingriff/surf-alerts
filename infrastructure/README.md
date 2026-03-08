# Infrastructure

AWS CDK (TypeScript) infrastructure for surf-alerts. See [docs/architecture/infrastructure.md](../docs/architecture/infrastructure.md) for full documentation.

## Commands

```bash
npm ci              # Install dependencies
npm run build       # Compile TypeScript
npm test            # Run CDK tests
npx cdk synth       # Synthesize CloudFormation
npx cdk deploy SufAlertsStack --require-approval never
```
