#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { CiIamStack } from "../lib/ci-iam-stack";
import { InfrastructureStack } from "../lib/infrastructure-stack";

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

new CiIamStack(app, "CiIamStack", {
  env,
  githubOwner: "benjamingriff",
  githubRepo: "surf-alerts",
});

new InfrastructureStack(app, "SufAlertsStack", { env });
